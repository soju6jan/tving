# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
from datetime import datetime
import time
# third-party
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify
from sqlalchemy import desc, or_

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, path_data, SystemModelSetting
from framework.job import Job
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from support.site.tving import SupportTving
from .model import ModelSetting, Episode
from .basic import TvingBasic

#########################################################
        
class TvingAuto(object):


    @staticmethod
    def scheduler_function():
        try:
            #logger.debug('start scheduler_function')
            import ffmpeg
            page = ModelSetting.get_int('auto_page')
            max_pf_count = ModelSetting.get('max_pf_count')
            save_path = ModelSetting.get('auto_save_path')
            default_quality = SupportTving.ins.get_quality_to_tving(ModelSetting.get('auto_quality'))
            retry_user_abort = ModelSetting.get_bool('retry_user_abort')
            except_channel = ModelSetting.get('except_channel')
            except_program = ModelSetting.get(key='except_program')
            download_qvod = ModelSetting.get_bool('download_qvod')
            download_program_in_qvod = ModelSetting.get('download_program_in_qvod')
            download_mode = ModelSetting.get(key='download_mode')
            whitelist_program = ModelSetting.get('whitelist_program')
            whitelist_first_episode_download = ModelSetting.get_bool('whitelist_first_episode_download')

            except_channels = [x.strip() for x in except_channel.replace('\n', ',').split(',')]
            except_programs = [x.strip().replace(' ', '') for x in except_program.replace('\n', ',').split(',')]
            download_program_in_qvods = [x.strip().replace(' ', '') for x in download_program_in_qvod.replace('\n', ',').split(',')]
            whitelist_programs = [x.strip().replace(' ', '') for x in whitelist_program.replace('\n', ',').split(',')]
            
            except_channels = Util.get_list_except_empty(except_channels)
            except_programs = Util.get_list_except_empty(except_programs)
            download_program_in_qvods = Util.get_list_except_empty(download_program_in_qvods)
            whitelist_programs = Util.get_list_except_empty(whitelist_programs)
            logger.debug('except_channels:%s', except_channels)
            logger.debug('except_programs:%s', except_programs)
            logger.debug('download_qvod :%s %s', download_qvod, type(download_qvod))
            logger.debug('download_program_in_qvods:%s', download_program_in_qvods)
            for i in range(1, page+1):
                vod_list = SupportTving.ins.get_vod_list(page=i)["result"]
                #for vod in [x for x in vod_list if x['episode']['drm_yn'].lower() != 'y']:
                for vod in vod_list:
                    try:
                        if not scheduler.is_include('tving_recent'):
                            logger.debug('not in scheduler')
                            return
                        code = vod["episode"]["code"]
                        #with db.session.no_autoflush:
                        if True:
                            # 2019-01-11 720권한만 있을 때 1080p를 받으려고 하면 계속 episode를 생성
                            #episode = db.session.query(Episode).filter_by(episode_code=code, quality=default_quality).with_for_update().first() 
                            #episode = db.session.query(Episode).filter_by(episode_code=code).with_for_update().first()
                            
                            # 2020-02-14 qvod episode_code 고정
                            episode = db.session.query(Episode).filter_by(episode_code=code, broadcast_date=str(vod["episode"]["broadcast_date"])[2:]).with_for_update().first()

                            if episode is not None:
                                logger.debug('program_name:%s frequency:%s %s %s', episode.program_name, episode.frequency, episode.user_abort, episode.retry)
                                if episode.completed:
                                    logger.debug('COMPLETED')
                                    continue
                                elif episode.user_abort:
                                    if retry_user_abort:
                                        episode.user_abort = False
                                    else:
                                        continue
                                elif episode.etc_abort > 10:
                                    # 1:알수없는이유 시작실패, 2 타임오버, 3, 강제스톱.킬
                                    # 12:제외채널, 13:제외프로그램
                                    # 14:화이트리스트
                                    # 9 : retry
                                    # 8 : qvod
                                    logger.debug('ETC ABORT:%s', episode.etc_abort)
                                    continue
                                elif episode.retry > 20:
                                    logger.debug('retry 20')
                                    episode.etc_abort = 15
                                    continue
                            # URL때문에 DB에 있어도 다시 JSON을 받아야함.
                            #json_data, url = TvingBasic.get_episode_json(code, default_quality)
                            json_data = SupportTving.ins.get_info(code, default_quality)
                            url = json_data['play_info']['url']
                            if episode is None:
                                #slogger.debug('EPISODE is none')
                                episode = Episode('auto')
                                episode = TvingBasic.make_episode_by_json(episode, json_data, url)
                                db.session.add(episode)
                            else:
                                episode = TvingBasic.make_episode_by_json(episode, json_data, url)

                            # qvod 체크
                            is_qvod = False
                            if url.find('quickvod') != -1:
                                is_qvod = True
                            
                            # 채널, 프로그램 체크
                            flag_download = True
                            if is_qvod:
                                if not download_qvod:
                                    flag_download = False
                                    for program_name in download_program_in_qvods:
                                        if episode.program_name.replace(' ', '').find(program_name) != -1:
                                            episode.etc_abort = 0
                                            flag_download = True
                                            logger.debug('is qvod.. %s %s', program_name, flag_download)
                                            break
                                    
                                    if not flag_download:
                                        episode.etc_abort = 8
                                        db.session.commit()
                                        logger.debug('is qvod.. pass')
                                        continue

                            if download_mode == '0':
                                for program_name in except_programs:
                                    if episode.program_name.replace(' ', '').find(program_name) != -1:
                                        episode.etc_abort = 13
                                        flag_download = False
                                        break

                                if episode.channel_name in except_channels:
                                    episode.etc_abort = 12
                                    flag_download = False
                            else:
                                if flag_download: #무조건 탐
                                    find_in_whitelist = False
                                    for program_name in whitelist_programs:
                                        if episode.program_name.replace(' ', '').find(program_name) != -1:
                                            find_in_whitelist = True
                                            break
                                    if not find_in_whitelist:
                                        episode.etc_abort = 14
                                        flag_download = False
                                if not flag_download and whitelist_first_episode_download and episode.frequency == 1:
                                    flag_download = True
                            if flag_download:
                                episode.etc_abort = 0
                                episode.retry += 1
                                episode.pf = 0 # 재시도
                                episode.save_path = save_path
                                episode.start_time = datetime.now()
                                db.session.commit()
                            else:
                                db.session.commit()
                                time.sleep(2)
                                continue
                            if json_data['drm'] == False:
                                logger.debug('FFMPEG Start.. id:%s', episode.id)
                                if episode.id is None:
                                    logger.debug('PROGRAM:%s', episode.program_name)
                                f = ffmpeg.Ffmpeg(url, episode.filename, plugin_id=episode.id, listener=TvingBasic.ffmpeg_listener, max_pf_count=max_pf_count, call_plugin='%s_recent' % package_name, save_path=save_path, headers=TvingBasic.get_headers(url))
                                f.start_and_wait()
                            else:
                                from .tving_dd import TvingDD
                                json_data['save_path'] = save_path
                                ret = TvingDD.download(json_data)
                                if ret:
                                    episode.completed = True
                                    episode.end_time = datetime.now()
                                    episode.download_time = (episode.end_time - episode.start_time).seconds
                                else:
                                    episode.etc_abort = 16
                                db.session.commit()


                    except Exception as e: 
                        logger.error('Exception:%s', e)
                        logger.error(traceback.format_exc())
                   
                    
                    #break
            #logger.debug('end scheduler_function')
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    


    @staticmethod
    def get_list(req):
        page_size = 20
        page = int(req.form['page']) if 'page' in req.form else 1
        option = req.form['option'] if 'option' in req.form else 'all'
        order = req.form['order'] if 'order' in req.form else 'desc'
        program = req.form['program'].strip() if 'program' in req.form else None
        #query = Episode.query.filter_by(call='auto')
        query = Episode.query.filter((Episode.call == 'auto') | (Episode.call == None))
        if program is not None:
            #query = query.filter(Episode.program_name.like('%'+program+'%'))
            query = query.filter(or_(Episode.program_name.like('%'+program+'%'), Episode.channel_name.like('%'+program+'%')))
        if option == 'completed':
            query = query.filter_by(completed=True)
        elif option == 'uncompleted':
            query = query.filter_by(completed=False)
        elif option == 'user_abort':
            query = query.filter_by(user_abort=True)
        elif option == 'pf_abort':
            query = query.filter_by(pf_abort=True)            
        elif option == 'etc_abort_under_10':
            query = query.filter(Episode.etc_abort < 10, Episode.etc_abort > 0) 
        elif option == 'etc_abort_8':
            query = query.filter_by(etc_abort='8')
        elif option == 'etc_abort_12':
            query = query.filter_by(etc_abort='12')
        elif option == 'etc_abort_13':
            query = query.filter_by(etc_abort='13')
        elif option == 'etc_abort_14':
            query = query.filter_by(etc_abort='14')
        if order == 'desc':
            query = query.order_by(desc(Episode.id))
        else:
            query = query.order_by(Episode.id)
        count = query.count()
        if page_size:
            query = query.limit(page_size)
        if page: 
            query = query.offset((page-1)*page_size)
        #return query
        tmp = query.all()
        ret = {}
        ret['paging'] = Util.get_paging_info(count, page, page_size)
        ret['list'] = [item.as_dict() for item in tmp]
        return ret



    @staticmethod
    def add_condition_list(req):
        try:
            mode = req.form['mode']
            value = req.form['value']
            old_value = ModelSetting.get(mode)
            entity_list = [x.strip().replace(' ', '') for x in old_value.replace('\n', ',').split(',')]
            if value.replace(' ', '') in entity_list:
                db.session.commit() 
                return 0
            else:
                if old_value != '':
                    old_value += ', '
                old_value += value
                ModelSetting.set(mode, old_value)
                return 1
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return -1
        finally:
            pass

    
    
    @staticmethod
    def reset_db():
        try:
            db.session.query(Episode).delete()
            db.session.commit()
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False
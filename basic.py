# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import time
import re
import urllib
from datetime import datetime

# third-party
from pytz import timezone
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify

# sjva 공용
from framework import app, db, scheduler, path_data
from framework.job import Job
import framework.tving.api as Tving

# 패키지
from .plugin import logger, package_name

import ffmpeg

from .model import ModelSetting, Episode


#########################################################
        
class TvingBasic(object):
    current_episode = None #다운받을 에피소드. 화면에서 정보를 보여주고 난 이후에 다운받기 ㄸ문
    db_default = { 
        'id' : '', 
        'pw' : '', 
        'token' : '',
        'quality' : 'FHD',
        'save_path' : os.path.join(path_data, 'download'),
        'max_pf_count' : '0',
        'login_type' : '0', 
        'use_proxy' : 'False',
        'proxy_url' : '',
        'device_id' : '',
        'recent_code' : ''
    }
    
    @staticmethod
    def db_init(data=None):
        try:
            if data is None:
                data = TvingBasic.db_default
            for key, value in data.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit() 
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def init():
        try:
            TvingBasic.db_init()
            #PooqBasic.login()
            #job = Job(package_name, '%s_login' % package_name, 60*24, PooqBasic.login, u"푹 Token 갱신을 위한 로그인", True)
            #scheduler.add_job_instance(job)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    
    @staticmethod
    def get_setting_value(key):
        try:
            return db.session.query(ModelSetting).filter_by(key=key).first().value
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def login():
        try:
            token = Tving.do_login(
                ModelSetting.get('id'), 
                ModelSetting.get('pw'), 
                ModelSetting.get('login_type')
            )
            if token is None:
                return False
            ModelSetting.set('token', token)
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def setting_save(req):
        try:
            flag_login = False
            for key, value in req.form.items():
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                if key == 'id' or key == 'pw':
                    if entity.value != value:
                        flag_login = True
                if entity is not None:
                    entity.value = value
            db.session.commit()                    
            if flag_login:
                if TvingBasic.login():
                    return 1
                else: 
                    return 2
            else:
                return 0 #저장
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def ffmpeg_listener(**arg):
        import ffmpeg
        refresh_type = None
        if arg['type'] == 'status_change':
            if arg['status'] == ffmpeg.Status.DOWNLOADING:
                episode = db.session.query(Episode).filter_by(id=arg['plugin_id']).with_for_update().first()
                episode.ffmpeg_status = int(arg['status'])
                db.session.commit()
            elif arg['status'] == ffmpeg.Status.COMPLETED:
                pass
            elif arg['status'] == ffmpeg.Status.READY:
                pass
        elif arg['type'] == 'last':
            episode = db.session.query(Episode).filter_by(id=arg['plugin_id']).with_for_update().first()
            episode.ffmpeg_status = int(arg['status'])
            if arg['status'] == ffmpeg.Status.WRONG_URL or arg['status'] == ffmpeg.Status.WRONG_DIRECTORY or arg['status'] == ffmpeg.Status.ERROR or arg['status'] == ffmpeg.Status.EXCEPTION:
                episode.etc_abort = 1
            elif arg['status'] == ffmpeg.Status.USER_STOP:
                episode.user_abort = True
                logger.debug('Status.USER_STOP received..')
            elif arg['status'] == ffmpeg.Status.COMPLETED:
                episode.completed = True
                episode.end_time = datetime.now()
                episode.download_time = (episode.end_time - episode.start_time).seconds
                episode.filesize = arg['data']['filesize']
                episode.filesize_str = arg['data']['filesize_str']
                episode.download_speed = arg['data']['download_speed']
                logger.debug('Status.COMPLETED received..')
            elif arg['status'] == ffmpeg.Status.TIME_OVER:
                episode.etc_abort = 2
            elif arg['status'] == ffmpeg.Status.PF_STOP:
                episode.pf = int(arg['data']['current_pf_count'])
                episode.pf_abort = 1
            elif arg['status'] == ffmpeg.Status.FORCE_STOP:
                episode.etc_abort = 3
            db.session.commit()
            #logger.debug('LAST commit %s', episode)
        elif arg['type'] == 'log':
            pass
        elif arg['type'] == 'normal':
            pass
        if refresh_type is not None:
            pass
   

    @staticmethod
    def make_episode_by_json(episode, data, vod_url):
        try:
            episode.episode_code = data["body"]["content"]["episode_code"]
            for q in data["body"]["stream"]["quality"]:
                if q['selected'] == 'Y':
                    episode.quality = q['code']
                    break
            episode.program_name = data["body"]["content"]["program_name"]
            episode.program_code = data["body"]["content"]["program_code"]
            episode.frequency = int(data["body"]["content"]["frequency"])
            episode.broadcast_date = str(data["body"]["content"]["info"]["episode"]["broadcast_date"])[2:]
            episode.channel_id = data["body"]["content"]["info"]["channel"]["code"]
            episode.channel_name = data["body"]["content"]["info"]["channel"]["name"]["ko"]
            episode.json = data
            episode.filename = Tving.get_filename(data)
            episode.vod_url = vod_url
            return episode
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.debug(data["body"]["content"]["program_name"])
    
    @staticmethod
    def analyze(url):
        try:
            logger.debug('analyze :%s', url)
            url_type = None
            code = None
            if url.startswith('http'):
                match = re.compile(r'player\/(?P<code>E\d+)').search(url)
                if match:
                    url_type = 'episode'
                    code = match.group('code')
            else:
                if url.startswith('E'):
                    url_type = 'episode'
                    code = url
                elif url.startswith('P'):
                    url_type = 'program'
                    code = url.strip()
                elif url.startswith('M'):
                    url_type = 'movie'
                    code = url.strip()
                else:
                    pass
            logger.debug('Analyze %s %s', url_type, code)
            ModelSetting.set('recent_code', code)
            if url_type is None:
                return {'url_type':'None'}
            elif url_type == 'episode':
                quality = ModelSetting.get('quality')
                quality = Tving.get_quality_to_tving(quality)
                data, vod_url = TvingBasic.get_episode_json(code, quality)
                logger.debug(vod_url)
                if data is not None:
                    episode = Episode('basic')
                    episode = TvingBasic.make_episode_by_json(episode, data, vod_url)
                    TvingBasic.current_episode = episode
                    return {'url_type': url_type, 'ret' : True, 'data' : episode.as_dict()}
                else:
                    return {'url_type': url_type, 'ret' : False, 'data' : data}
            elif url_type == 'program':
                data = Tving.get_vod_list(Tving.config['program_param'] % code, page=1)
                return {'url_type': url_type, 'page':'1', 'code':code, 'data' : data}
            elif url_type == 'movie':
                proxy_url = ModelSetting.get('proxy_url') if ModelSetting.get_bool('use_proxy') else None
                data = Tving.get_movie_json(code, ModelSetting.get('device_id'), proxy_url, ModelSetting.get('token'))

                
                return {'url_type': url_type, 'page':'1', 'code':code, 'data' : data}

        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())        

    @staticmethod
    def download_url(url, filename):
        try:
            save_path = ModelSetting.get('save_path')
            max_pf_count = ModelSetting.get('max_pf_count')
            TvingBasic.current_episode.start_time = datetime.now()
            db.session.add(TvingBasic.current_episode)
            db.session.commit()
            f = ffmpeg.Ffmpeg(url, TvingBasic.current_episode.filename, plugin_id=TvingBasic.current_episode.id, listener=TvingBasic.ffmpeg_listener, max_pf_count=max_pf_count, call_plugin='tving_basic', save_path=save_path)
            #f.start_and_wait()
            f.start()
            #time.sleep(60)
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc()) 

    @staticmethod
    def movie_download(url, filename):
        try:
            save_path = ModelSetting.get('save_path')
            logger.debug(save_path)
            max_pf_count = ModelSetting.get('max_pf_count')
            f = ffmpeg.Ffmpeg(url, filename, plugin_id=-1, listener=None, max_pf_count=max_pf_count, call_plugin='tving_basic', save_path=save_path)
            #f.start_and_wait()
            f.start()
            #time.sleep(60)
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc()) 


    
    @staticmethod
    def analyze_program_page(code, page):
        try:
            data = Tving.get_vod_list(Tving.config['program_param'] % code, page=int(page))
            return {'url_type': 'program', 'page':page, 'code':code, 'data' : data}
            
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())        

    @staticmethod
    def get_episode_json(code, quality):
        try:
            use_proxy = ModelSetting.get('use_proxy')
            proxy_url = ModelSetting.get('proxy_url')
            token = ModelSetting.get('token')
            #logger.debug('get_episode_json %s %s', use_proxy, proxy_url)
            if use_proxy == 'True':
                ret =  Tving.get_episode_json_proxy(code, quality, proxy_url, token=token)
            else:
                ret = Tving.get_episode_json_default(code, quality, token=token)
            #logger.debug(ret)
            return ret
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc()) 

# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
from datetime import datetime
import time
import Queue
import threading
# third-party
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify
from sqlalchemy import desc, or_

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, path_data
from framework.job import Job
from framework.util import Util

# 패키지
from .plugin import logger, package_name
import framework.tving.api as Tving
from .model import ModelSetting, Episode
from .basic import TvingBasic
import plugin

#########################################################


class TvingProgramEntity(object):

    current_entity_id = 1
    entity_list = []

    def __init__(self, episode_code, quality):
        self.entity_id = TvingProgramEntity.current_entity_id
        TvingProgramEntity.current_entity_id += 1
        self.episode_code = episode_code
        self.quality = quality
        self.ffmpeg_status = -1
        self.ffmpeg_status_kor = u'대기중'
        self.ffmpeg_percent = 0
        self.created_time = datetime.now().strftime('%m-%d %H:%M:%S')
        self.json_data = None
        self.ffmpeg_arg = None
        self.cancel = False

        TvingProgramEntity.entity_list.append(self)

    
    @staticmethod
    def get_entity(entity_id):
        for _ in TvingProgramEntity.entity_list:
            if _.entity_id == entity_id:
                return _
        return None
    

class TvingProgram(object):
    recent_code = None

    # 다운로드 목록
    download_queue = None

    download_thread = None

    #max_ffmpeg_count = 2

    current_ffmpeg_count = 0

    

    @staticmethod
    def start():
        try:
            if TvingProgram.download_queue is None:
                TvingProgram.download_queue = Queue.Queue()
            
            if TvingProgram.download_thread is None:
                TvingProgram.download_thread = threading.Thread(target=TvingProgram.download_thread_function, args=())
                TvingProgram.download_thread.daemon = True  
                TvingProgram.download_thread.start()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def download_program(req):
        try:
            episode_code = req.form['code']
            quality = req.form['quality']
            TvingProgram.download_program2(episode_code, quality)
            return 'success'
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return 'fail'

    @staticmethod
    def download_program2(episode_code, quality):
        try:
            TvingProgram.start()
            entity = TvingProgramEntity(episode_code, quality)
            ret = TvingBasic.get_episode_json(entity.episode_code, entity.quality)
            entity.json_data = ret[0]
            TvingProgram.download_queue.put(entity)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def download_thread_function():
        while True:
        #while self.flag_stop == False:
            try:
                while True:
                    if TvingProgram.current_ffmpeg_count < int(TvingBasic.get_setting_value('program_auto_count_ffmpeg')):
                        break
                    time.sleep(5)

                entity = TvingProgram.download_queue.get()
                if entity.cancel:
                    continue
                # 초기화
                if entity is None:
                    return
                #Log('* 스캔 큐 AWAKE : %s', self.current_scan_entity.filename)
                #self.current_scan_entity.status = 'SCAN_START' 
                
                #self.current_scan_entity.scan_start_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                #Log('* 스캔 큐 scan_start_time : %s', self.current_scan_entity.scan_start_time)
                Tving._token = ModelSetting.get('token')
                data, vod_url = TvingBasic.get_episode_json(entity.episode_code, entity.quality)
                #logger.debug(data)
        
                episode = Episode('basic')
                episode = TvingBasic.make_episode_by_json(episode, data, vod_url)
                #TvingBasic.current_episode = episode
                entity.json_data['filename'] = episode.filename
                #if TvingProgram.current_ffmpeg_count < TvingProgram.max_ffmpeg_count: 
                import ffmpeg
                max_pf_count = ModelSetting.get('max_pf_count')
                save_path = ModelSetting.get('program_auto_path')

                if TvingBasic.get_setting_value('program_auto_make_folder') == 'True':
                    program_path = os.path.join(save_path, data['body']['content']['program_name'])
                    save_path = program_path
                try:
                    if not os.path.exists(save_path):
                        os.makedirs(save_path)
                except:
                    logger.debug('program path make fail!!')
                # 파일 존재여부 체크
                if os.path.exists(os.path.join(save_path, episode.filename)):
                    entity.ffmpeg_status_kor = '파일 있음'
                    entity.ffmpeg_percent = 100
                    plugin.socketio_list_refresh()
                    continue

                f = ffmpeg.Ffmpeg(vod_url, episode.filename, plugin_id=entity.entity_id, listener=TvingProgram.ffmpeg_listener, max_pf_count=max_pf_count, call_plugin='%s_program' % package_name, save_path=save_path)
                f.start()
                TvingProgram.current_ffmpeg_count += 1
                    
                TvingProgram.download_queue.task_done()    

                """
                self.current_scan_t = ScanThread()
                self.current_scan_t.set(self.current_scan_entity, self.wait_event)
                self.current_scan_t.start()
                Log('* 스캔 큐 thread 종료 대기')
                self.current_scan_t.join(60*10)
                if self.current_scan_t.is_alive():
                    Log('* 스캔 큐 still Alive')
                    self.current_scan_t.process.terminate()
                    self.current_scan_t.join()
                Log('process returncode %s', self.current_scan_t.process.returncode)

                self.current_scan_t = None
                # 초기화 한번 체크
                if self.flag_stop: return
                self.current_scan_entity.status = 'SCAN_COMPLETED' 
                self.current_scan_entity.scan_end_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.scan_queue.task_done()
                Log('* 남은 큐 사이즈 : %s', self.scan_queue.qsize())
                self.current_scan_entity = None
                """
                #time.sleep(100) 
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        

    @staticmethod
    def ffmpeg_listener(**arg):
        #logger.debug(arg)
        import ffmpeg
        refresh_type = None
        if arg['type'] == 'status_change':
            if arg['status'] == ffmpeg.Status.DOWNLOADING:
                """
                episode = db.session.query(Episode).filter_by(id=arg['plugin_id']).with_for_update().first()
                episode.ffmpeg_status = int(arg['status'])
                db.session.commit()
                """
                pass
            elif arg['status'] == ffmpeg.Status.COMPLETED:
                pass
            elif arg['status'] == ffmpeg.Status.READY:
                pass
        elif arg['type'] == 'last':
            TvingProgram.current_ffmpeg_count += -1
            """
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
            """
            pass
        elif arg['type'] == 'log':
            pass
        elif arg['type'] == 'normal':
            
            pass
        if refresh_type is not None:
            pass
        

        entity = TvingProgramEntity.get_entity(arg['plugin_id'])
        if entity is None:
            return
        entity.ffmpeg_arg = arg
        entity.ffmpeg_status = int(arg['status'])
        entity.ffmpeg_status_kor = str(arg['status'])
        entity.ffmpeg_percent = arg['data']['percent']

        import plugin
        arg['status'] = str(arg['status'])
        plugin.socketio_callback('status', arg)
    
    @staticmethod
    def program_auto_command(req):
        try:
            command = req.form['command']
            entity_id = int(req.form['entity_id'])
            logger.debug('command :%s %s', command, entity_id)
            entity = TvingProgramEntity.get_entity(entity_id)
            
            ret = {}
            if command == 'cancel':
                if entity.ffmpeg_status == -1:
                    entity.cancel = True
                    entity.ffmpeg_status_kor = "취소"
                    plugin.socketio_list_refresh()
                    ret['ret'] = 'refresh'
                elif entity.ffmpeg_status != 5:
                    ret['ret'] = 'notify'
                    ret['log'] = '다운로드중 상태가 아닙니다.'
                else:
                    idx = entity.ffmpeg_arg['data']['idx']
                    import ffmpeg
                    ffmpeg.Ffmpeg.stop_by_idx(idx)
                    #plugin.socketio_list_refresh()
                    ret['ret'] = 'refresh'

            elif command == 'reset':
                if TvingProgram.download_queue is not None:
                    with TvingProgram.download_queue.mutex:
                        TvingProgram.download_queue.queue.clear()
                    for _ in TvingProgramEntity.entity_list:
                        if _.ffmpeg_status == 5:
                            import ffmpeg
                            idx = _.ffmpeg_arg['data']['idx']
                            ffmpeg.Ffmpeg.stop_by_idx(idx)
                    #with TvingProgram.download_queue.mutex:
                    #    TvingProgram.download_queue.queue.clear()
                TvingProgramEntity.entity_list = []
                plugin.socketio_list_refresh()
                ret['ret'] = 'refresh'
            elif command == 'delete_completed':
                new_list = []
                for _ in TvingProgramEntity.entity_list:
                    if _.ffmpeg_status_kor in ['파일 있음', '취소', 'URL실패']:
                        continue
                    if _.ffmpeg_status != 7:
                        new_list.append(_)
                TvingProgramEntity.entity_list = new_list
                plugin.socketio_list_refresh()
                ret['ret'] = 'refresh'
            
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['ret'] = 'notify'
            ret['log'] = str(e)
        return ret
    
    @staticmethod
    def download_program_check(req):
        ret = {}
        try:
            logger.debug(req.form)
            data = req.form['data']
            logger.debug(data)

            lists = data[:-1].split(',')
            count = 0
            for _ in lists:
                code, quality = _.split('_')
                TvingProgram.download_program2(code, quality)
                count += 1
            ret['ret'] = 'success'
            ret['log'] = count
            
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            ret['ret'] = 'fail'
            ret['log'] = str(e)

        return ret
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
# 패키지
from .plugin import logger, package_name

import ffmpeg

from .model import ModelSetting, Episode
from support.site.tving import SupportTving

#########################################################
        
class TvingBasic(object):
    current_episode = None #다운받을 에피소드. 화면에서 정보를 보여주고 난 이후에 다운받기 ㄸ문
    

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
            episode.episode_code = data["content"]["episode_code"]
            for q in data["stream"]["quality"]:
                if q['selected'] == 'Y':
                    episode.quality = q['code']
                    break
            episode.program_name = data["content"]["program_name"]
            episode.program_code = data["content"]["program_code"]
            episode.frequency = int(data["content"]["frequency"])
            episode.broadcast_date = str(data["content"]["info"]["episode"]["broadcast_date"])[2:]
            episode.channel_id = data["content"]["info"]["channel"]["code"]
            episode.channel_name = data["content"]["info"]["channel"]["name"]["ko"]
            episode.json = data
            episode.filename = SupportTving.ins.get_filename(data)
            if vod_url.find('quickvod') != -1:
                episode.filename = episode.filename.replace('-ST.mp4', '-STQ.mp4')
            episode.vod_url = vod_url
            return episode
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.debug(data["content"]["program_name"])
    
    @staticmethod
    def analyze(url):
        try:
            logger.debug('analyze :%s', url)
            url_type = None
            code = None
            match = re.compile(r'(?P<code>[EMP]\d+)').search(url)
            if match:
                code = match.group('code')
                if code.startswith('E'):
                    url_type = 'episode'
                elif code.startswith('P'):
                    url_type = 'program'
                elif code.startswith('M'):
                    url_type = 'movie'
            logger.debug('Analyze %s %s', url_type, code)
            if url_type is None:
                return {'url_type':'None'}
            elif url_type == 'episode':
                data = TvingBasic.get_episode_json(code)
                vod_url = data['url'] 
                logger.debug(vod_url)
                if data is not None:
                    episode = Episode('basic')
                    episode = TvingBasic.make_episode_by_json(episode, data, vod_url)
                    TvingBasic.current_episode = episode
                    return {'url_type': url_type, 'ret' : True, 'code': code, 'data':data, 'info' : episode.as_dict()}
                else:
                    return {'url_type': url_type, 'ret' : False, 'data' : {'message': '에피소드 정보를 얻지 못함'}}
            elif url_type == 'program':
                data = SupportTving.ins.get_vod_list(program_code=code)
                return {'url_type': url_type, 'page':'1', 'code':code, 'data' : data}
            elif url_type == 'movie':
                data = TvingBasic.get_episode_json(code)
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

            #logger.error(TvingBasic.get_headers(url))
            f = ffmpeg.Ffmpeg(url, TvingBasic.current_episode.filename, plugin_id=TvingBasic.current_episode.id, listener=TvingBasic.ffmpeg_listener, max_pf_count=max_pf_count, call_plugin='tving_basic', save_path=save_path, headers=TvingBasic.get_headers(url))
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
            data = SupportTving.ins.get_vod_list(program_code=code, page=page)
            return {'url_type': 'program', 'page':page, 'code':code, 'data' : data}
            
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())        

    @staticmethod
    def get_episode_json(code, quality=None):
        try:
            if quality == None:
                quality = ModelSetting.get('quality')
                quality = SupportTving.ins.get_quality_to_tving(quality)                
            data = SupportTving.ins.get_info(code, quality)
            return data
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc()) 

    @staticmethod
    def get_headers(url):
        if 'quickvod' in url:
            params = {}
            for tmp in url.split('?')[1].split('&'):
                tmp2 = tmp.split('=')
                params[tmp2[0]] = tmp2[1]
            cookie = f"CloudFront-Key-Pair-Id={params['Key-Pair-Id']}; CloudFront-Policy={params['Policy']}; CloudFront-Signature={params['Signature']};"
            headers = {'Cookie':cookie}
            return headers


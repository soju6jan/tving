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
from framework.logger import get_logger
from framework.job import Job
from framework.util import Util
#import framework.tving.api as Tving

# 패키지
from .plugin import logger, package_name
import ffmpeg
from .model import ModelSetting
from .basic import TvingBasic
from .auto import TvingAuto
#from .logic_basic import LogicBasic
#from .logic_recent import LogicRecent

# 로그
#########################################################
        
class Logic(object):
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
        'recent_code' : '',

        'auto_interval' : '10', 
        'auto_start' : 'False', 
        'auto_quality' : 'FHD',        
        'retry_user_abort' : 'False',
        'except_channel' : '',
        'except_program' : '',
        'auto_page' : '2',
        'auto_save_path' : os.path.join(path_data, 'download'),
        'download_mode' : '0',
        'whitelist_program' : '', 
        'whitelist_first_episode_download' : 'True',

        'program_auto_path' : os.path.join(path_data, 'download'),
        'program_auto_make_folder' : 'True', 
        'program_auto_count_ffmpeg' : '4', 
    }
    

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            logger.debug('%s plugin_load', package_name)
            # DB 초기화
            Logic.db_init()
            TvingBasic.login()

            if ModelSetting.get('auto_start') == 'True':
                Logic.scheduler_start()

            # 편의를 위해 json 파일 생성
            from plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
            scheduler.remove_job('%s_recent' % package_name)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_start():
        try:
            interval = ModelSetting.get('auto_interval')
            job = Job(package_name, '%s_recent' % package_name, interval, Logic.scheduler_function, u"티빙 최신 TV VOD 다운로드", True)
            scheduler.add_job_instance(job)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())


    @staticmethod
    def scheduler_stop():
        try:
            scheduler.remove_job(package_name)
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
                if LogicBasic.login():
                    return 1
                else: 
                    return 2
            return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            logger.error('key:%s value:%s', key, value)
            return False


    @staticmethod
    def scheduler_function():
        try:
            TvingAuto.scheduler_function()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    # 기본 구조 End
    ##################################################################


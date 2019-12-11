# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import logging
import urllib
import json

# third-party
import requests
from flask import Blueprint, request, Response, send_file, render_template, redirect, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from flask_socketio import SocketIO, emit, send

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, socketio
from framework.util import Util, AlchemyEncoder

# 로그
package_name = __name__.split('.')[0].split('_sjva')[0]
logger = get_logger(package_name)

# 패키지
import framework.tving.api as Tving
from .basic import TvingBasic
from .auto import TvingAuto
from .model import ModelSetting
from .logic_program import TvingProgram, TvingProgramEntity
#########################################################


blueprint = Blueprint(package_name, package_name, url_prefix='/%s' %  package_name, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
menu = {
    'main' : [package_name, '티빙'],
    'sub' : [
        ['basic', '기본'], ['recent', '최근방송 자동'], ['program', '프로그램별 자동'], ['log', '로그']
    ]
} 

plugin_info = {
    'version' : '0.1.0.0',
    'name' : '티빙 다운로드',
    'category_name' : 'vod',
    'icon' : '',
    'developer' : 'soju6jan',
    'description' : '티빙에서 VOD 다운로드',
    'home' : 'https://github.com/soju6jan/tving_sjva',
    'more' : '',
}

def plugin_load():
    logger.debug('plugin_load:%s', package_name)
    TvingBasic.init()
    TvingAuto.init()
    TvingProgram.init()
    #import platform
    #if platform.system() != 'Windows':
    #    TvingAuto.init()
    #    pass

def plugin_unload():
    logger.debug('plugin_unload:%s', package_name)

   

#########################################################
# WEB Menu                                    
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/recent' % package_name)

@blueprint.route('/<sub>', methods=['GET', 'POST'])
@login_required
def first_menu(sub):
    if sub == 'basic':
        try:
            return redirect('/%s/%s/setting' % (package_name, sub))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'recent':
        try:
            return redirect('/%s/%s/list' % (package_name, sub))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'program':
        try:
            return redirect('/%s/%s/select' % (package_name, sub))
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))


@blueprint.route('/<sub>/<sub2>')
@login_required
def second_menu(sub, sub2):
    if sub == 'basic':
        if sub2 == 'setting':
            try:
                setting_list = db.session.query(ModelSetting).all()
                arg = Util.db_list_to_dict(setting_list)
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'download':
            try:
                arg = {}
                arg["code"] = request.args.get('code')
                if arg['code'] is None:
                    arg['code'] = ModelSetting.get('recent_code')
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
    elif sub == 'recent':
        if sub2 == 'setting':
            try:
                setting_list = db.session.query(ModelSetting).all()
                arg = Util.db_list_to_dict(setting_list)
                arg['scheduler'] = str(scheduler.is_include(package_name))
                arg['is_running'] = str(scheduler.is_running(package_name))
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'list':
            try:
                arg = {}
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
    elif sub == 'program':
        if sub2 == 'setting':
            try:
                setting_list = db.session.query(ModelSetting).all()
                arg = Util.db_list_to_dict(setting_list)
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'list':
            try:
                arg = {}
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub2 == 'select':
            try:
                setting_list = db.session.query(ModelSetting).all()
                arg = Util.db_list_to_dict(setting_list)
                arg["code"] = request.args.get('code')
                if arg['code'] is None:
                    arg["code"] = ModelSetting.get('recent_code')
                return render_template('%s_%s_%s.html' % (package_name, sub, sub2), arg=arg)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))




#########################################################
# For UI                                                            
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
def ajax(sub):
    logger.debug('TVING AJAX sub:%s', sub)
    try:     
        if sub == 'setting_save':
            try:
                ret = TvingBasic.setting_save(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')
        elif sub == 'login':
            try:
                ret = Tving.do_login(request.form['id'], request.form['pw'], request.form['login_type'] )
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')
        elif sub == 'analyze':
            url = request.form['url']
            ret = TvingBasic.analyze(url)
            TvingProgram.recent_code = url
            return jsonify(ret)
        elif sub == 'program_page':
            code = request.form['code']
            page = request.form['page']
            ret = TvingBasic.analyze_program_page(code, page)
            return jsonify(ret)
        elif sub == 'episode_download_url':
            logger.debug(request.form)
            url = request.form['url']
            filename = request.form['filename']
            logger.debug('download %s %s', url, filename)
            ret = TvingBasic.download_url(url, filename)
            return jsonify(ret)
        elif sub == 'movie_download':
            try:
                url = request.form['url']
                filename = request.form['filename']
                ret = TvingBasic.movie_download(url, filename)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        # 자동
        elif sub == 'scheduler':
            try:
                go = request.form['scheduler']
                logger.debug('scheduler :%s', go)
                if go == 'true':
                    TvingAuto.scheduler_start()
                else:
                    TvingAuto.scheduler_stop()
                return jsonify(go)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
                return jsonify('fail')
        # 자동 목록
        elif sub == 'auto_list':
            try:
                ret = TvingAuto.get_list(request)
                logger.debug('len list :%s', len(ret))
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub == 'add_condition_list':
            try:
                ret = TvingAuto.add_condition_list(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        
        elif sub == 'reset_db':
            try:
                ret = TvingAuto.reset_db()
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())  
        elif sub == 'download_program':
            try:
                ret = TvingProgram.download_program(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())  
        elif sub == 'download_program_list':
            try:
                ret = TvingProgram.download_program()
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        elif sub == 'program_auto_command':
            try:
                ret = TvingProgram.program_auto_command(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())

        elif sub == 'download_program_check':
            try:
                ret = TvingProgram.download_program_check(request)
                return jsonify(ret)
            except Exception as e: 
                logger.error('Exception:%s', e)
                logger.error(traceback.format_exc())
        



                
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


#########################################################
# For UI                                                            
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
def api(sub):
    if sub == 'decrypt':
        try: 
            import system
            sjva_token = request.args.get('sjva_token')
            if sjva_token != system.SystemLogic.get_setting_value('unique'):
                return "wrong_sjva_token"
            code = request.args.get('c')
            quality = request.args.get('q')
            token = request.args.get('t')
            logger.debug(token)
            #logger.debug(token)
            token = '_tving_token=%s' % urllib.quote(token)
            logger.debug(token)
            use_proxy = ModelSetting.get('use_proxy')
            proxy_url = ModelSetting.get('proxy_url')
            #logger.debug('get_episode_json %s %s', use_proxy, proxy_url)
            if use_proxy == 'True':
                ret =  Tving.get_episode_json_proxy(code, quality, proxy_url, token=token)
            else:
                ret = Tving.get_episode_json_default(code, quality, token=token)
            return ret[1]
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return str(e)        


sid_list = []
@socketio.on('connect', namespace='/%s' % package_name)
def connect():
    try:
        logger.debug('socket_connect')
        sid_list.append(request.sid)
        tmp = None
        
        #if Logic.current_data is not None:
        data = [_.__dict__ for _ in TvingProgramEntity.entity_list]
        tmp = json.dumps(data, cls=AlchemyEncoder)
        tmp = json.loads(tmp)
        emit('on_connect', tmp, namespace='/%s' % package_name)
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())


@socketio.on('disconnect', namespace='/%s' % package_name)
def disconnect():
    try:
        sid_list.remove(request.sid)
        logger.debug('socket_disconnect')
    except Exception as e: 
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())

def socketio_callback(cmd, data):
    if sid_list:
        tmp = json.dumps(data, cls=AlchemyEncoder)
        tmp = json.loads(tmp)
        socketio.emit(cmd, tmp , namespace='/%s' % package_name, broadcast=True)

def socketio_list_refresh():
    data = [_.__dict__ for _ in TvingProgramEntity.entity_list]
    tmp = json.dumps(data, cls=AlchemyEncoder)
    tmp = json.loads(tmp)
    socketio_callback('list_refresh', tmp)
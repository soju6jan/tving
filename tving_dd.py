import os, sys, traceback
from support.base import d
from framework import path_data
from .plugin import logger

class TvingDD:
    @classmethod
    def download(cls, data):
        try:
            from lib_wvtool import WVDownloader
            from support.base import SupportUtil
            if SupportUtil.is_arm():
                return False
            downloader = WVDownloader({
                'code' : data['content']['episode_code'],
                'mpd_url' : data['play_info']['uri'],
                'output_filepath' : os.path.join(data['save_path'], data['filename']),
                'license_headers' : data['play_info']['drm_key_request_properties'],
                'license_url' : data['play_info']['drm_license_uri'],
                'folder_tmp' : os.path.join(path_data, 'tmp'),
            })
            ret = downloader.download()
            return ret
        except Exception as e:
            logger.error(f"Exception:{str(e)}")
            logger.error(traceback.format_exc())
            return False

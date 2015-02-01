# coding=utf8

import os
import re
import time
import sys
import requests
from clint.textui.progress import Bar
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
from ConfigParser import SafeConfigParser


print """   ,---,                  ,-.
,`--.' |              ,--/ /| ,-.----.
|   :  :      ,---, ,--. :/ | \    /  \                ,---,
:   |  '  ,-+-. /  |:  : ' /  |   :    |           ,-+-. /  |
|   :  | ,--.'|'   ||  '  /   |   | .\ :   ,---.  ,--.'|'   |
'   '  ;|   |  ,"' |'  |  :   .   : |: |  /     \|   |  ,"' |
|   |  ||   | /  | ||  |   \  |   |  \ : /    /  |   | /  | |
'   :  ;|   | |  | |'  : |. \ |   : .  |.    ' / |   | |  | |
|   |  '|   | |  |/ |  | ' \ \:     |`-''   ;   /|   | |  |/
'   :  ||   | |--'  '  : |--' :   : :   '   |  / |   | |--'
;   |.' |   |/      ;  |,'    |   | :   |   :    |   |/
'---'   '---'       '--'      `---'.|    \   \  /'---'
                                `---`     `----'"""


artist_tpl = u'<b>Исполнитель</b>: {0}\n'
album_tpl = u'<b>Альбом</b>: {0}\n'
country_tpl = u'<b>Cтрана</b>: {0}\n'
year_tpl = u'<b>Год</b>: {0}\n'
style_tpl = u'<b>Стиль</b>: {0}\n'
duration_tpl = u'<b>Продолжительность</b>: {0}\n'
codec_tpl = u'<b>Кодек</b>: {0}\n'
tracklist_tpl = u'\n<b>Треклист</b>:\n{0}\n\n'

ex_url = 'http://www.ex.ua'
fs_id_regex = r'swfu_fs_id = (\d+);'
upload_url_pattern = 'http://fs{0}.www.ex.ua/r_upload'
metadata_file_name = 'metadata.py'
config = None
auth_cookie = None


class Album():
    def __init__(self, album_path):
        self.path = album_path
        print self.path
        files = os.listdir(self.path)
        if metadata_file_name not in files:
            raise Exception(metadata_file_name+' file not found in '+self.path)
        files.remove(metadata_file_name)
        self.files = files

    def get_files(self):
        return self.files

    def get_data(self):
        try:
            with open(self.path+'/'+metadata_file_name, 'r') as mdata:
                d = {}
                exec mdata.read()
                name = d['NAME']
                avatar = config.get('Avatars', str(d['AVATAR']))
                description = artist_tpl.format(d['ARTIST']) + \
                    album_tpl.format(d['ALBUM']) + \
                    country_tpl.format(d['COUNTRY']) + \
                    year_tpl.format(d['YEAR']) + \
                    style_tpl.format(d['STYLE']) + \
                    duration_tpl.format(d['DURATION']) + \
                    codec_tpl.format(d['CODEC']) + \
                    tracklist_tpl.format(d['TRACKLIST']) + \
                    d['OTHER']
                return name, description, avatar
        except Exception:
            raise Exception('Cannot read metadata file in '+self.path)


class ProgressBar():
    def __init__(self, length):
        self.bar = Bar(expected_size=length, filled_char='=')
        self.status = 0

    def increment(self, value):
        self.status += value

    def progress(self, value):
        self.bar.show(self.status + value)


def upload():
    global config
    config = read_config()
    music_albums = scan_music()
    confirm = raw_input('Enter "y" to upload or any key to cancel: ')
    if confirm == 'y':
        log_in()
        publish(music_albums)
        print 'Upload complete!'
    else:
        print 'Aborted'


def read_config():
    print 'Initialize...'
    parser = SafeConfigParser()
    parser.read('config.ini')
    return parser


def scan_music():
    print 'Scanning music...'
    root_folder = config.get('Music', 'root_folder')
    folders = os.listdir(root_folder)
    return [Album(root_folder+'/'+folder) for folder in folders]


def log_in():
    print 'Logging in...'
    auth_data = {
        'login': config.get('Account', 'login'),
        'password': config.get('Account', 'password')
    }
    global auth_cookies
    auth_cookies = requests.post(ex_url+'/login', data=auth_data, allow_redirects=False).cookies
    if not auth_cookies:
        raise Exception('Login error!')
    print 'Login successful!'


def send_files(encoders, url):
    total_size = reduce(lambda x, y: x+len(y), encoders, 0)
    bar = ProgressBar(total_size)
    for encoder in encoders:
        uploaded = False
        retries = 0
        monitor = MultipartEncoderMonitor(encoder, lambda m: bar.progress(m.bytes_read))
        while not uploaded:
            try:
                response = requests.post(url, data=monitor, headers={'Content-Type': monitor.content_type})
            except Exception as e:
                print 'ERROR: ' + str(e)
            else:
                if response.status_code == 200:
                    uploaded = True
                    bar.increment(len(encoder))
                else:
                    print 'ERROR: ' + response.reason
            finally:
                if not uploaded:
                    if retries < 3:
                        retries += 1
                        print 'Retrying... {0}/3'.format(retries)
                    else:
                        print 'Upload failed after 3 retries!'
                        sys.exit(1)


def publish(albums):
    print 'Uploading albums...'
    article_data = {
        'original_id': config.get('Section', 'original_id'),
        'link_id': config.get('Section', 'link_id')
    }
    publish_section_id = config.get('Section', 'publish_section_id')
    albums_count = len(albums)
    for i in range(albums_count):
        album = albums[i]
        edit_article_page = requests.get(ex_url+'/edit', params=article_data, cookies=auth_cookies)
        fs_id = re.search(fs_id_regex, edit_article_page.text).group(1)
        article_id = edit_article_page.url[22:]
        u_key = auth_cookies['ukey']
        name, description, avatar = album.get_data()
        print 'Uploading {0}/{1} {2}'.format(i+1, albums_count, name)
        encoders = []
        for _file in album.get_files():
            file_data = {'file': (_file, open(album.path+'/'+_file, 'rb'), 'application/octet-stream'),
                         'key': u_key, 'time': str(time.time()), 'object_id': article_id}
            encoders.append(MultipartEncoder(file_data))
        send_files(encoders, upload_url_pattern.format(fs_id))
        article_contents = {
            'avatar_id': avatar,
            'post':	description,
            'public': config.get('Section', 'public'),
            'title': name
        }
        requests.post(ex_url+'/r_edit/'+article_id, data=article_contents, cookies=auth_cookies)
        requests.get(ex_url+'/add_link/'+article_id, params={'link_id': '4'}, cookies=auth_cookies)
        publish_data = {
            'back': '/user/Inkpen',
            'object_{0}'.format(article_id): '1'
        }
        requests.post(ex_url+'/include/'+publish_section_id, data=publish_data, cookies=auth_cookies)
        requests.get(ex_url+'/clean_buffer', cookies=auth_cookies)
        print '\rDone'+(' '*70)


if __name__ == '__main__':
    try:
        upload()
    except KeyboardInterrupt:
        print 'INTERRUPTED!'
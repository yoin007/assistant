# _*_ coding: utf-8 _*_
# @Time: 2024/09/24 16:47
# @Author: Tech_T


import csv
import os
import re

import requests

from config import config
from config.config import Config
from config.log import LogConfig
from function.api import ju_pai
from sendqueue import QueueDB

log = LogConfig().get_logger()


class Manage:
    def __init__(self):
        self.stop_func = []
        self.ban_csv = 'function/manage/ban.csv'
        self.ban = self.get_ban()

    # 读取违禁词
    def get_ban(self):
        if not os.path.exists(self.ban_csv):
            return []
        with open(self.ban_csv, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            self.ban = [row[0] for row in reader]
            return self.ban

    # 添加违禁词
    def add_ban(self, word):
        with open(self.ban_csv, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([word])
        self.ban.append(word)
        log.info(f'{word} 已添加到违禁词列表')

    # 删除违禁词
    def del_ban(self, word):
        with open(self.ban_csv, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows([row for row in self.ban if row[0] != word])
        self.ban = [row[0] for row in self.ban if row[0] != word]
        log.info(f'{word} 已从违禁词列表中删除')

    def del_chatroom_member(self, wxid, chatroom):
        if wxid in Config().get_config('admin_list'):
            return False
        if chatroom not in Config().get_config('admin_chatroom'):
            return False
        wcf_http_url = Config().get_config('wcf_http_url')
        url = f'{wcf_http_url}delete-chatroom-member'
        headers = {'accept': 'application/json',
                   'Content-Type': 'application/json'}
        data = {
            'wxids': wxid,
            'roomid': chatroom
        }
        response = requests.post(url, headers=headers, json=data)
        # http端的响应没有做区分，所有及时是删除失败，也会返回200
        if response.status_code == 200:
            log.info(f'{wxid} 已从 {chatroom} 中移除')
            return True
        else:
            log.error(f'移除 {wxid} 失败，错误信息：{response.text}')
            return False

# 新版本中 该功能已移除
# async def auto_new_friend(record: any):
#     xml_data = record.parsexml
#     parse_xml = json.loads(str(xml_data))
#     v3 = parse_xml['@encryptusername'],
#     v4 = parse_xml['@ticket'],
#     scene = int(parse_xml['@scene'])
#     with QueueDB() as q:
#         q.accept_new_friend(record.id, scene, v3[0], v4[0], 'manage')


def say_hi_qun(record: any):
    """
    新人入群欢迎，小黄人举牌
    """
    alias = ''
    if "加入了群聊" in record.content:
        s_list = record.content.split('"')
        alias = s_list[-2]
    if "通过扫描" in record.content:
        s_list = record.content.split('"')
        alias = s_list[1]
    if alias:
        img = ju_pai(alias)
        if img:
            with QueueDB() as q:
                q.send_image(record.id, img, record.roomid, 'manage')
                log.info(f"欢迎 {alias} 加入群聊 {record.roomid}")
                return True


async def hi_to_new_friend(record: any):
    if say_hi_qun(record):
        return
    content = record.content
    if "You" in content:
        nick_name = re.findall(
            r"You have added (.*) as your Weixin contact. Start chatting!", content)
    else:
        nick_name = re.findall(r"你已添加了(.*)，现在可以开始聊天了。", content)

    if nick_name:
        with QueueDB() as q:
            q.send_text(
                record.id, f"Hi~, {nick_name[0]}, 我已经通过了你的好友请求。", record.sender, 'manage')


async def invite_chatroom_member(record: any):
    text = record.content
    roomids = Config().get_config('invite_rooms')
    print(roomids.keys())
    if text in roomids.keys():
        room_id = roomids[text]
        print(room_id)
        with QueueDB() as q:
            q.cr_members(
                record.id, room_id, record.sender, 'manage')
            log.info(f"邀请 {record.sender} 加入群聊 {room_id}")

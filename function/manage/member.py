# _*_ coding :utf-8 _*_
# @Time : 2024/09/28 18:20
# @Author : Tech_T

import re
import requests
import sqlite3

from config.config import Config
from config.log import LogConfig

config = Config()
log = LogConfig().get_logger()


class Member:
    def __enter__(self, db='databases/member.db'):
        self.__conn__ = sqlite3.connect(db)
        self.__cursor__ = self.__conn__.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__conn__.close()
    # -----------------------------create table---------------------------------
    def __create_table__(self):
        try:
            self.__cursor__.execute("""
            CREATE TABLE member(
                uuid TEXT PRIMARY KEY,
                wxid TEXT,
                alias TEXT,
                score INTEGER DEFAULT 50,
                balance INTEGER DEFAULT 0,
                level INTEGER DEFAULT 5,
                module TEXT,
                birthday TEXT,
                activate BOOLEAN DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                note TEXT)""")
            self.__conn__.commit()
            log.info('表：member 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：member 已存在, 跳过创建')
            else:
                log.error('表：member 创建失败')
                raise e

        try:
            self.__cursor__.execute("""
            CREATE TABLE contacts(
                wxid TEXT PRIMARY KEY,
                remark TEXT,
                name TEXT,
                gender INTEGER,
                city TEXT,
                province TEXT,
                country TEXT,
                code TEXT)""")
            self.__conn__.commit()
            log.info('表：contacts 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：contacts 已存在, 跳过创建')
            else:
                log.error('表：contacts 创建失败')
                raise e
            
        try:
            self.__cursor__.execute("""
            CREATE TABLE score_record(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT,
                source_id TEXT,
                event TEXT,
                type TEXT,
                score INTEGER,
                left_score INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            self.__conn__.commit()
            log.info('表：score_history 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：score_history 已存在, 跳过创建')
            else:
                log.error('表：score_history 创建失败')
                raise e
            
        try:
            self.__cursor__.execute("""
            CREATE TABLE score_type(
                event TEXT PRIMARY KEY,
                type TEXT,
                score INTEGER,
                money float,
                note TEXT)""")
            self.__conn__.commit()
            log.info('表：score_type 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：score_type 已存在, 跳过创建')
            else:
                log.error('表：score_type 创建失败')
                raise e
    
        try:
            self.__cursor__.execute("""
            CREATE TABLE permission(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                func_name TEXT,
                func TEXT,
                active BOOLEAN DEFAULT 1,
                black_list TEXT,
                white_list TEXT,
                type TEXT,
                pattern TEXT,
                need_at BOOLEAN DEFAULT 0,
                reply TEXT,
                module TEXT,
                level TEXT,
                example TEXT,
                score_event TEXT)""")
            self.__conn__.commit()
            log.info('表：permission 创建成功')
        except sqlite3.OperationalError as e:
            if 'already exists' in str(e):
                log.info('表：permission 已存在, 跳过创建')
            else:
                log.error('表：permission 创建失败')
                raise e
    
    @staticmethod
    def wx_contacts():
        wcf_http_url = Config().get_config('wcf_http_url')
        response = requests.get(wcf_http_url + 'contacts')
        return response.json()['data']['contacts']
    # -------------------------table: contacts---------------------------------
    # 获取所有微信联系人
    def update_contacts(self):
        members = self.__cursor__.execute("SELECT wxid FROM contacts").fetchall()
        members = [member[0] for member in members]
        contacts = self.wx_contacts()
        # print(contacts)
        for contact in contacts:
            if contact['wxid'] not in members:
                self.__cursor__.execute("INSERT INTO contacts (wxid, remark, name, gender, city, province, country, code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (contact['wxid'], contact['remark'], contact['name'], contact['gender'], contact['city'], contact['province'], contact['country'], contact['code']))
                # print( contact['wxid'] + ' 插入成功')
            else:
                self.__cursor__.execute("UPDATE contacts SET remark = ?, name = ?, gender = ?, city = ?, province = ?, country = ?, code = ? WHERE wxid = ?", (contact['remark'], contact['name'], contact['gender'], contact['city'], contact['province'], contact['country'], contact['code'], contact['wxid']))
                # print(contact['wxid'] + ' 更新成功')
        self.__conn__.commit()
        self.__conn__.close()
        log.info('联系人更新成功')
    
    def wxid_name(self, wxid):
        """
        从 contacts 表中获取 wxid 对应的 name
        :param wxid: 微信id
        :return: name
        """
        self.__cursor__.execute("SELECT name FROM contacts WHERE wxid = ?", (wxid,))
        result = self.__cursor__.fetchone()
        return result[0] if result else None

    
    # -------------------------table: member---------------------------------
    def insert_member(self, uuid, wxid, alias, note=''):
        """
        往数据库添加会员信息
        :param uuid: 会员uuid
        :param wxid: 会员wxid
        :param alias: 会员别名
        :param note: 备注
        """
        self.__cursor__.execute("INSERT INTO member (uuid, wxid, alias, module, birthday, note) VALUES (?, ?, ?, 'basic','', ?)", (uuid, wxid, alias, note))
        self.__conn__.commit()
    
    def member_info(self, uuid):
        """
        查询会员信息
        :param uuid: 会员uuid
        :return: 会员信息
        """
        self.__cursor__.execute("SELECT * FROM member WHERE uuid = ?", (uuid,))
        result = self.__cursor__.fetchone()
        result = result if result else None
        return result

    # -------------------------table: score---------------------------------
    def event_score(self, uuid, event, left_score):
        """
        1. 根据 event 查询对应的积分变化
        2. 计算积分变化
        3. 添加记录到 score_record 表中
        4. 调用 update_score 更新会员积分
        :param uuid: 会员uuid
        :param event: 事件
        :param left_score: 剩余积分
        """
        pass

    # -------------------------table: permission---------------------------------
    def permission_info(self, func_name=''):
        """
        查询权限信息
        :param func_name: 函数名
        :return: 权限信息
        """
        if func_name == '':
            self.__cursor__.execute("SELECT * FROM permission")
            result = self.__cursor__.fetchall()
            return result if result else None
        else:
            self.__cursor__.execute("SELECT * FROM permission WHERE func_name = ?", (func_name,))
            result = self.__cursor__.fetchone()
            return result if result else None
    
    def inactive_func(self, func_name):
        """
        停用函数
        :param func_name: 函数名
        """
        c = self.__cursor__.execute("UPDATE permission SET active = 0 WHERE func_name = ?", (func_name,))
        if c.rowcount == 0:
            log.error(f'停用函数失败：{func_name}')
        else:
            self.__conn__.commit()
            log.info(f'停用函数：{func_name}')
    
    def active_func(self, func_name):
        """
        启用函数
        :param func_name: 函数名
        """
        self.__cursor__.execute("UPDATE permission SET active = 1 WHERE func_name = ?", (func_name,))
        self.__conn__.commit()
        log.info(f'启用函数：{func_name}')


async def insert_member(record):
    """
    插入会员信息
    :param record: 会员信息
    """
    if '@chatroom' in record.roomid:
        pattern = r'@(.*?)\u2005'
        matches = re.findall(pattern, record.content)
        at_list = record.parsexml.replace('"', '').split(',')[1:]
        print(matches, at_list)
        with Member() as m:
            if len(at_list) == len(matches):
                for k, v in zip(at_list, matches):
                    uuid = k + '#' + record.roomid
                    row = m.member_info(uuid)
                    if row:
                        log.info(f'会员已存在：{uuid}')
                    else:
                        m.insert_member(uuid, k, v)
                        log.info(f'添加会员：{uuid}, {k}, {v}')

            else:
                log.error(f'添加会员出错：{record.id} - {record.content}')
    else:
        try:
            member_str = record.content.replace('：', ':').replace(' ', '').split(':')[1]
            member_list = member_str.split(',') 
            with Member() as m:
                for member in member_list:
                    row = m.member_info(member)
                    if row:
                        log.info(f'会员已存在：{member}')
                    else:
                        alias = m.wxid_name(member)
                        if alias:
                            m.insert_member(member, member, alias)
                            log.info(f'添加会员：{member}, {member}, {alias}')
                        else:
                            m.update_contacts()
                            alias = m.wxid_name(member)
                            if alias:
                                m.insert_member(member, member, alias)
                                log.info(f'添加会员：{member}, {member}, {alias}')
                            else:
                                log.error(f'添加会员出错：{record.id} - {record.content}')
        except Exception as e:
            log.error(f'添加会员出错：{record.id} - {record.content} - {e}')
                        
def check_permission(func):
    def wrapper(pos, record, *args, **kwargs):
        if has_permission(pos, func, record, *args, **kwargs):
            return func(record, *args, **kwargs)
        else:
            log.warning(f"{record.id} - {func.__name__}：鉴权失败")
    return wrapper
        
def has_permission(pos, func, record, *args, **kwargs):
    """
    鉴权
    :param pos: 位置参数， 调用时会多出一个参数
    :param func: 被装饰的函数
    :param record: 
    """
    print(pos)
    if record.is_group:
        uuid = record.sender + '#' + record.roomid
    else:
        uuid = record.sender
    func_name = func.__name__
    with Member() as m:
        permission = m.permission_info(func_name)
        member_info = m.member_info(uuid)
        if member_info:
            if permission:
                if permission[9] in member_info[6].split('/'):
                    if int(member_info[5]) >= int(permission[10]):
                        log.info(f"{record.id} - {func_name}：权限通过")
                        return True
                    else:
                        log.warning(f"{record.id} - {func_name}：{uuid}-会员等级不足")
                else:
                    log.warning(f"{uuid}-尚未开通 {permission[9]} 模块权限")
            else:
                log.warning(f"{func_name} 尚未开启权限检测，请检查配置")
        else:
            log.warning(f"{uuid} 尚未开通会员")
    return False

async def start_func(record: any):
    if record.sender not in config.get_config('admin_list'):
        return False
    pattern = r"^START (.*)"
    match = re.search(pattern, record.content)
    if match:
        func_name = match.group(1)
        try:
            with Member() as m:
                m.active_func(func_name)
                return True
        except Exception as e:
            log.error(f"start_func Failed: {e}")
            return False
    
async def stop_func(record: any):
    if record.sender not in config.get_config('admin_list'):
        return False
    pattern = r"^STOP (.*)"
    match = re.search(pattern, record.content)
    if match:
        func_name = match.group(1)
        try:
            with Member() as m:
                m.inactive_func(func_name)
                return True
        except Exception as e:
            log.error(f"stop_func Failed: {e}")
            return False
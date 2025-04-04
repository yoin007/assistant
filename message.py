# _*_ coding: utf-8 _*_
# @Time: 2024/09/23 20:43
# @Author: Tech_T


import json
import re
import sqlite3
import time
import xmltodict

from config.log import LogConfig
from config.config import Config
from function.manage.manage import Manage
from function.manage.member import wxid_name_remark
from sendqueue import QueueDB

log = LogConfig().get_logger()
config = Config()

class Record:
    def __init__(self, body: dict):
        self.id: str = str(body.get("id"))
        self.sender: str = body.get("sender")
        self.roomid: str = body.get("roomid") if body.get('roomid') else self.sender
        self.thumb: str = body.get("thumb")
        self.is_at: bool = body.get("is_at")
        self.is_self: bool = body.get("is_self")
        self.is_group: bool = body.get("is_group")
        self.extra: str = body.get("extra")
        self.timestamp = body.get("ts")
        self.xml = body.get("xml", '')
        if self.is_group:
            self.alias = self.get_alias(self.sender, self.roomid)  # 该方法尚未实现
        else:
            self.alias = ''

        # 调整 type 字段，细化类型:
        # 1-文本 3-图片 34-语音 42-个人或公众号名片 42-企业微信名片 43-视频 47-动画表情 48-定位 10000-系统提示 49-应用
        # 4956-引用 493-音乐 495-网页链接 496-文件 4916-卡券 4919-聊天记录 4933-小程序 492000-转账
        # 新增 parsexml 字段，对纯文本以外其他类型的消息，提供了 xml 的字典解析
        self.type, self.content, self.parsexml = self.parse(body.get('type'), body.get('content'))

        # 消息存入本地数据库
        with MessageDB() as db:
            db.insert(self.__dict__)
            self.log_record()

    def log_record(self):
        loginfo = f""
        if self.is_self:
            loginfo += f"### 发送消息 {self.id} ###\n接收人:"
        else:
            loginfo += f"### 收到消息 {self.id} ###\n发送人:"
        if self.is_group:
            room_remark = wxid_name_remark(self.roomid)
            loginfo += f"{room_remark[0]}[{self.roomid}]-{self.alias}[{self.sender}]"
        else:
            remark = wxid_name_remark(self.roomid)
            loginfo += f"{remark[1]}[{self.roomid}]"
        loginfo += f"\n消息类型: {self.type}"
        loginfo += f"\n消息内容: {self.content}"
        loginfo += f"\nextra: {self.extra}"
        loginfo += f"\nxml: {self.xml}"
        log.info(loginfo)

        self.check_ban()

    def get_alias(self, wxid, roomid):
        with QueueDB() as q:
            alias = q.alias(wxid, roomid)
            return alias

    # 检查违禁词
    def check_ban(self):
        if not self.is_group:
            return False
        m = Manage()
        fb_words = m.get_ban()
        for word in fb_words:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            if bool(pattern.search(self.content)):
                m.del_chatroom_member(self.sender, self.roomid)
                with QueueDB() as q:
                    q.send_text(self.id, f"🛩️🛩️'抱歉，用户 {self.alias} 因为您违反了群聊规定,现将你移除群聊", self.roomid, self.sender, 'Record')
    
    # xml 解析
    def parse(self, msg_type, content):
        match msg_type:
            # 已知：朋友圈为0
            case 0:
                return 0, content, {}
            # 文本
            case 1:
                msgsource = xmltodict.parse(self.xml).get('msgsource') if self.xml else None
                atuserlist = msgsource.get('atuserlist', None) if msgsource else None
                return 1, content, atuserlist 
            # 图片
            case 3:
                # 引用消息循环解析的错误处理
                parse_xml = xmltodict.parse(content).get('msg') if content and '<img' in content else None
                return 3, f"[图片]", parse_xml
            # 语音
            case 34:
                # 引用消息循环解析的错误处理
                parse_xml = xmltodict.parse(content).get('msg') if content and '<voicemsg' in content else None
                # 计算语音时长输出到content
                voice_len = f"{int(parse_xml['voicemsg']['@voicelength']) / 1000} 秒" if parse_xml else ''
                return 34, f"[语音] {voice_len}", parse_xml
            # 好友确认，自动添加好友
            case 37:
                parse_xml = xmltodict.parse(content).get('msg') if content else None
                return 37, f"[好友确认]", parse_xml
            # possiblefriend_msg
            case 40:
                return 40, f"[POSSIBLEFRIEND_MSG]", {}
            # 名片
            case 42:
                parse_xml = xmltodict.parse(content).get('msg') if content else None
                # 判断是个人名片还是公众号，带名字输出到content
                card_type = '公众号名片' if parse_xml['@certflag'] == '24' else '个人名片'
                name = parse_xml['@nickname']
                return 42, f"[{card_type}] {name}", parse_xml
            # 视频
            case 43:
                parse_xml = xmltodict.parse(content).get('msg') if content and '<video' in content else None
                return 43, f"[视频]", parse_xml
            # 动画表情
            case 47:
                # 引用消息循环解析的错误处理
                parse_xml = xmltodict.parse(content).get('msg') if content and '<emoji' in content else None
                # 如果cdnurl域名为 wxapp.tc.qq.com,就可以直接访问到表情，因此赋值给 extra
                if parse_xml:
                    cdnurl = parse_xml['emoji']['@cdnurl']
                    self.extra = cdnurl.replace('&amp;', '&') if 'wxapp.tc.qq.com' in cdnurl else self.extra
                return 47, f"[动画表情]", parse_xml
            # 定位
            case 48:
                parse_xml = xmltodict.parse(content).get('msg')
                # 提取定位的地名和标签赋值到content
                poiname = parse_xml.get('location').get('@poiname')
                label = parse_xml.get('location').get('@label')
                # 提取兴趣点poiid 拼接一个url赋值到extra
                poiid = parse_xml.get('location').get('@poiid')
                self.extra = 'https://map.qq.com/poi/?sm=' + poiid.split('_')[1] if poiid else self.extra
                return 48, f"[位置] {poiname} {label}", parse_xml
            # VOIPMSG
            case 50:
                return 50, f"[VOIPMSG]", {}
            # 微信初始化
            case 51:
                return 51, f"[微信初始化]", {}
            # VOIPNOTIFY
            case 52:
                return 52, f"[VOIPNOTIFY]", {}
            # VOIPINVITE
            case 53:
                return 53, f"[VOIPINVITE]", {}
            # 小视频
            case 62:
                return 62, f"[小视频]", {}
            # 企业微信名片
            case 66:
                parse_xml = xmltodict.parse(content).get('msg')
                # 将名字输出到content
                name = parse_xml.get('@nickname')
                return 66, f"[企业微信名片] {name}", parse_xml
            # SYSNOTICE
            case 9999:
                return 9999, f"[SYSNOTICE]", {}
            # 系统提示
            case 10000:
                return 10000, content, {}
            # 撤回消息
            case 10002:
                if self.sender == 'newsapp':
                    return 10002, f"[newsapp]", {}
                if self.sender == 'weixin':
                    return 10002, f"[微信团队]", {}
                try:
                    m_id = xmltodict.parse(content).get('sysmsg').get('revokemsg').get('newmsgid')
                    mdb = MessageDB()
                    mdb.__enter__()
                    msg = mdb.select_content(m_id)
                    mdb.__exit__()
                    with QueueDB() as q:
                        q.send_text(self.id, msg, Config.get_config('admin'), '', 'Record')
                except Exception as e:
                    if str(e) == 'revokemsg':
                        return 10002, f"[系统消息 10002]", {}
                    with QueueDB() as q:
                        q.send_text(self.id, str(e), Config.get_config('admin'), '', 'Record')
                    return 10002, f"[撤回消息] {str(e)}", {}
            # 应用
            case 49:
                parse_xml = xmltodict.parse(content).get('msg')
                appmsg = parse_xml.get('appmsg')
                msg_type = int(appmsg.get('type'))

                match msg_type:
                    # 音乐
                    case 3:
                        # 提取歌曲标题、歌曲描述、歌曲链接输出到content
                        title = appmsg.get('title')
                        desc = appmsg.get('des')
                        musicurl = appmsg.get('url')
                        # 提取歌曲音频数据url赋值到extra
                        self.extra = appmsg.get('dataurl')
                        # 提取歌曲封面到 thumb
                        self.thumb = appmsg.get('songalbumurl')
                        return 493, f"[音乐] <{title}> {desc}({musicurl})", parse_xml
                    # 引用消息中的音乐
                    case 76:
                        # 在引用消息中，音乐的type字段会变成76
                        # 提取歌曲标题、歌曲描述、歌曲链接输出到content
                        title = appmsg.get('title')
                        desc = appmsg.get('des')
                        musicurl = appmsg.get('url')
                        # 提取歌曲音频数据url赋值到extra
                        self.extra = appmsg.get('dataurl')
                        # 提取歌曲封面到 thumb
                        self.thumb = appmsg.get('songalbumurl')
                        return 4976, f"[引用消息中的音乐] <{title}> {desc}({musicurl})", parse_xml
                    # 网页
                    case 5:
                        # 提取标题、描述、链接
                        title, desc, url = appmsg.get('title'), appmsg.get('des'), appmsg.get('url')
                        self.extra = url
                        return 495, f"[链接] <{title}> {desc}({url})", parse_xml
                    # 文件
                    case 6:
                        # 提取文件标题
                        # print('File')
                        title = appmsg.get('title')
                        path = self.extra
                        # print(title, path)
                        return 496, f"[文件] <{title}>", parse_xml
                    # 卡券
                    case 16:
                        # 提取卡券标题、描述
                        title, desc = appmsg.get('title'), appmsg.get('desc')
                        # 提取LOGO到thumb
                        self.thumb = appmsg.get('thumburl')
                        return 4916, f"[卡券] <{title}> {desc}", parse_xml
                    # 位置共享
                    case 17:
                        return 4917, f"{self.sender} 发起了 [位置共享]", parse_xml
                    # 合并转发
                    case 19:
                        # 提取合并转发标题、描述
                        title, desc = appmsg.get('title'), appmsg.get('des')
                        # 重构聊天消息列表，清除不易阅读的信息
                        if appmsg.get('recorditem'):
                            recorditem = xmltodict.parse(appmsg.get('recorditem')).get('recordinfo')
                            datalist = recorditem.get('datalist').get('dataitem')
                            recorditem['datalist'] = [
                                {
                                    'type': int(item.get('@datatype', 0)),
                                    'content': ' '.join([item.get('datatitle', ''), item.get('datadesc', '')]),
                                    'name': item.get('sourcename', ''),
                                    'avatar': item.get('sourceheadurl', ''),
                                    'time': item.get('soucetime', ''),
                                    'timestamp': int(item.get('srcMsgCreateTime', 0))
                                }
                                for item in datalist
                            ]
                            self.extra = recorditem
                        return 4919, f"[合并转发] <{title}> {desc}", parse_xml
                    # 引用
                    case 57:
                        # 提取实际消息
                        title = appmsg.get('title')
                        refermsg = appmsg.get('refermsg')
                        # 错误处理：当循环解析为 引用 类型时，最终会遇到refermsg 为None 的情况，因此加判读语句
                        refer_type = int(refermsg.get('type', 0)) if refermsg else 0
                        refer_content = refermsg.get('content', '') if refermsg else ''
                        # 对引用内容的 xml 进行循环解析
                        if '<msg>' in refer_content and '</msg>' in refer_content:
                            self.extra = self.parse(refer_type, refer_content)[1]
                        else:
                            # 如果非 xml, 则直接返回文本
                            self.extra = refer_content
                        return 4957, f"[引用消息] <{title}> {self.extra}", parse_xml
                    # 转账
                    case 2000:
                        title, des = appmsg.get('title'), appmsg.get('des')
                        # 提取接收转账用的 transferid 到 extra
                        self.extra = {
                            'transferid': appmsg.get('wcpayinfo').get('transferid'),
                            'wxid': self.sender
                        }
                        return 2000, f"[转账] <{title}> {des}", parse_xml
                # 当49类型消息有其他子类型未匹配到时，返回空，忽略该消息
                return 49, f'[未知消息类型] {appmsg.get("type")}', parse_xml
        # 当有其他类型的消息未匹配到的时候，返回空，忽略该消息
        log.error(f'未匹配到消息类型: {msg_type} - {content}')
        return msg_type, f'[未知消息类型] {content}', {}

        
class MessageDB:
    def __enter__(self, db = 'databases/messages.db'):
        self.__conn__ = sqlite3.connect(db)
        self.__cursor__ = self.__conn__.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__conn__.commit()
        self.__conn__.close()

    def __create_table__(self):
        self.__cursor__.execute('''
            CREATE TABLE IF NOT EXISTS messages(
            id TEXT PRIMARY KEY,
            sender TEXT,
            roomid TEXT,
            alias TEXT,
            thumb TEXT,
            is_at BOOLEAN,
            is_self BOOLEAN,
            is_group BOOLEAN,
            extra TEXT,
            type INTEGER,
            content TEXT,
            parsexml TEXT,
            timestamp INTEGER)''')
        self.__conn__.commit()

    def insert(self, record):
        # print(record)
        record['extra'] = json.dumps(record['extra'], ensure_ascii=False) if isinstance(record['extra'], dict) else record['extra']
        record['parsexml'] = json.dumps(record['parsexml'], ensure_ascii=False)
        self.__cursor__.execute('INSERT INTO messages VALUES(:id, :sender, :roomid, :alias, :thumb, :is_at, :is_self, :is_group, :extra, :type, :content, :parsexml, :timestamp)', record)
        self.__conn__.commit()

    def select(self, m_id):
        self.__cursor__.execute('SELECT * FROM messages WHERE id = ?', (m_id,))
        result = self.__cursor__.fetchone()
        result = result if result else None
        return result
    
    def select_content(self, m_id):
        self.__cursor__.execute('SELECT content FROM messages WHERE id = ?', (m_id,))
        result = self.__cursor__.fetchone()
        result = result[0] if result else None
        return result

# _*_ coding: utf-8 _*_
# @Time : 2024/09/23 11:27
# @Author : Tech_T
# @python: 3.10.14

import asyncio
import random
import re
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

import function
from config.log import LogConfig
from config.config import Config
from function.manage.member import Member
from function.manage.manage import Manage
from function.task import task_start
from message import Record
from sendqueue import QueueDB

# 导入配置
config = Config()
wcf, timer, timer_random = config.get_config('wcf_http_url'), config.get_config(
    'queue_timer'), config.get_config('queue_timer_random')

# 导入日志
log = LogConfig().get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时运行的代码
    tasks = [
        asyncio.create_task(consume_queue_timer()),
        asyncio.create_task(task_start()),
    ]

    try:
        yield
    finally:
        # 关闭时运行的代码
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(lifespan=lifespan)


async def consume_queue_timer():
    while True:
        with QueueDB() as q:
            q.__consume__()
        random_sec = random.randint(*timer_random)
        # print(f"等待{random_sec}秒")
        # await asyncio.sleep(random.randint(*timer_random))
        await asyncio.sleep(random_sec)


@app.post('/')
async def root(request: Request):
    body = await request.json()
    record = Record(body)
    # 消息类型：
    # 1-文本 3-图片 34-语音 42-个人或公众号名片 42-企业微信名片 43-视频 47-动画表情 48-定位 10000-系统提示
    # 49-应用 4957-引用 493-音乐 495-网页链接 496-文件 4916-卡券 4919-聊天记录 4933-小程序 492000-转账

    if record.type == 495:
        print('网页链接', record.content)

    # 自动回复匹配
    reply, func_name = trigger(record.roomid, record.content, record.is_at, str(
        record.type), record.sender, record.id)

    # 如果匹配到 reply, 则直接回复
    if reply:
        with QueueDB() as q:
            aters = record.sender if record.is_group else ''
            q.send_text(record.id, reply, record.roomid, aters, 'root')

    # 如果匹配到 func_name, 则执行对应函数
    if func_name:
        func = getattr(function, func_name)
        if func:
            log.info(f'执行函数: {func_name}')
            asyncio.create_task(func(record))
        else:
            log.error(f'函数 {func_name} 无法执行，请检查配置')


def trigger(roomid, content, is_at, record_type, sender, mid):
    # with open("config/tigger.yaml", "r", encoding="utf-8") as f:
    #     data = yaml.safe_load(f)
    manager = Manage()
    fb_words = manager.get_ban()
    for word in fb_words:
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        if bool(pattern.search(content)):
            with QueueDB() as q:
                q.send_text(
                    mid, f"🛩️🛩️'抱歉，微信用户 {sender} 因为违反了群聊规定,现将你移除群聊", roomid, '', 'trigger')
                manager.del_chatroom_member(sender, roomid)
            return None, None

    with Member() as m:
        rules = m.permission_info()
        if rules:
            for rule in rules:
                msg_type = rule[6] if rule[6] else 'all'
                pattern = rule[7] if rule[7] else ''
                reply = rule[9] if rule[9] else ''
                row = {
                    'blacklist': rule[4].split('/') if rule[4] else [],
                    'whitelist': rule[5].split('/') if rule[5] else [],
                    'type': msg_type,
                    'pattern': pattern,
                    'need_at': rule[8] if rule[8] else 0,
                    'reply': reply,
                    'func_name': rule[1]
                }
                # print(row)
                # 如果改函数被禁用，则跳过
                if rule[3] == 0:
                    continue
                # 判断消息类型，匹配特定消息类型
                rec_type = row.get('type', 'all')
                if rec_type != 'all':
                    if str(record_type) != rec_type:
                        continue
                if row['need_at'] and not is_at:
                    continue
                # 如果命中黑名单，则跳过
                if roomid in row['blacklist']:
                    continue
                # 判断 白名单 是否为 all
                if row['whitelist'] == ['all']:
                    if re.search(row['pattern'], content, re.DOTALL):
                        return row['reply'], row['func_name']
                    else:
                        continue
                # 判断 白名单 是否为空
                if row['whitelist'] and roomid not in row['whitelist']:
                    continue
                # print(content, roomid)
                # 判断是否匹配
                if not re.search(row['pattern'], content, re.DOTALL):
                    continue
                return row['reply'], row['func_name']
    # 如果没有命中规则，则返回 None
    return None, None


if __name__ == "__main__":
    try:
        # uvicorn.run('main:app', host='0.0.0.0', port=9988, reload=True)  # app
        uvicorn.run('main:app', host='0.0.0.0', port=8899, reload=True)  # dev
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")

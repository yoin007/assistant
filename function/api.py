# _*_ coding :utf-8 _*_
# @Time :2024/09/27 09:44
# @Author : Tech_T


import asyncio
import os
import re
import time
import requests
import json
from zhipuai import ZhipuAI
from urllib.parse import quote
from config.config import Config
from sendqueue import QueueDB

config = Config()

def send_remind(tips, receiver, aters = '', produce = 'api'):
    mid = str(time.time().__int__())
    with QueueDB() as q:
        q.send_text(mid, tips, receiver, aters, produce)
    time.sleep(1)


async def zhaosheng_assistant(record):
    text = record.content
    pattern = r'@天龙招生助理\s*(.*)'
    match = re.search(pattern, text)
    if match:
        user_message = match.group(1)
        zs_config = config.get_config('zhaosheng')
        token = zs_config['token']
        assistant_id = zs_config['assistant_id']
        user_id = zs_config['user_id']
        # 定义 API 的 URL
        url = 'https://yuanqi.tencent.com/openapi/v1/agent/chat/completions'

        # 定义请求头
        headers = {
            'X-Source': 'openapi',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'  # 使用传入的 token
        }

        # 定义请求体
        data = {
            "assistant_id": assistant_id,
            "user_id": user_id,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_message  # 使用传入的用户消息
                        }
                    ]
                }
            ]
        }

        # 发送 POST 请求
        response = requests.post(url, headers=headers, json=data)  # 使用 json 参数自动设置正确的 Content-Type

        # 返回响应内容
        try:
            rsp = response.json()["choices"][0]['message']['content']
        except json.decoder.JSONDecodeError:
            rsp = "抱歉，我无法回答该问题，请致电：88857277"
    else:
        rsp = "抱歉，我无法回答该问题，请致电：88857277"
    send_remind(rsp, record.roomid, record.sender)


def one_day_English():
    # 原来是每日一句英语，但是api失效，更改为下面的每日一句
    url = 'https://api.ahfi.cn/api/bsnts?type=text'
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/119.0.6045.160 Safari/537.36 '
    }
    # 发送GET请求
    response = requests.get(url, headers).text
    return response

def get_joke():
    # 接口域名
    url = 'https://apis.tianapi.com/joke/index'
    # 参数
    params = {
        'key': config.get_config('joke_key'),
        'num': 1
    }
    # 将参数编码为表单数据
    data = requests.compat.urlencode(params)
    # 请求头
    headers = {
        'Content-type': 'application/x-www-form-urlencoded'
    }
    # 发送POST请求
    response = requests.post(url, data=data, headers=headers)
    # 获取响应内容
    result = response.text
    # 将JSON字符串解析为字典
    joke = json.loads(result)['result']['list'][0]['content']
    # 打印结果
    # print(joke)
    return joke

def ju_pai(words):
    root = os.getcwd()
    pic = os.path.join(root, 'xiaohuangren.png')
    headers = {
        'authority': 'api.ahfi.cn',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,'
                  'application/signed-exchange;v=b3;q=0.7',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/119.0.6045.160 Safari/537.36 '
    }
    from urllib.parse import quote
    encoded_words = quote(f"欢迎{words}入群!")
    req = requests.get(f"https://api.ahfi.cn/api/xrjupai?msg={encoded_words}", headers=headers, verify=False)
    with open(pic, 'wb') as f:
        f.write(req.content)
    if req.status_code == 200:
        return pic
    else:
        ''
    
def holiday():
    req = requests.get('http://timor.tech/api/holiday/tts', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)','accept': 'application/json'}).json()
    if req['code'] == 0:
        return req['tts']
    else:
        return ''

def get_weather(city='李沧'):
    key = config.get_config('weather_key')
    url = f'http://apis.juhe.cn/simpleWeather/query?city={quote(city)}&key={key}'
    headers = {
        'accept': 'application/json',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
    }
    print(url)
    response = requests.get(url, headers=headers).json()
    if response['reason'] == '查询成功!':
        weather = response['result']
        return weather
    else:
        return ''

async def weather_report(record: any):
    text = record.content
    resp = f"{record.content}:\n"
    try:
        pattern = r"(.*?)的天气"

        match = re.search(pattern, text)
        if match:
            city = match.group(1)
        else:
            city = '青岛'
        weather_report = get_weather(city)
        if weather_report:
            weather_tip = ''
            realtime = weather_report['realtime']
            weather = {'温度': realtime['temperature'], '湿度': realtime['humidity'], '天气': realtime['info'], '风向': realtime['direct'], '风力': realtime['power'], '空气质量': realtime['aqi']}
            for k,v in weather.items():
                weather_tip = weather_tip + f'{k}：{v}\t'
            future_list = weather_report['future']
            future_report = '未来5天天气：\n'
            for future in future_list:
                future_report += future['date'] + '\n温度：' + future['temperature'] + '\t天气：' + future['weather'] + '\t风向：' + future['direct'] + '\n'
            resp += weather_tip + '\n\n' + future_report
        else:
            resp += '查询失败'

    except Exception as e:
        print(str(e))
        resp += str(e)
    print(resp, record.roomid)
    send_remind(resp, record.roomid, 'weather')
    return "Fail"
    
async def zhipu_answer(record: any):
    text = record.content
    match = re.search(r'^zp-(.*)', text)
    if match:
        question = match.group(1)
    else:
        send_remind('智谱问答出错，请联系管理员', record.roomid, 'zhipu')
        return 0 
    key = Config().get_config("zhipu_key")
    client = ZhipuAI(api_key=key)
    response = client.chat.asyncCompletions.create(
        model="glm-4-plus",  # 请填写您要调用的模型名称
        messages=[
            {
                "role": "user",
                "content": question
            }
        ],
    )
    task_id = response.id
    task_status = ''
    get_cnt = 0

    while task_status != 'SUCCESS' and task_status != 'FAILED' and get_cnt <= 40:
        result_response = client.chat.asyncCompletions.retrieve_completion_result(id=task_id)
        # print(result_response)
        task_status = result_response.task_status

        await asyncio.sleep(6)
        get_cnt += 1
    answer = result_response.choices[0].message.content
    send_remind(answer, record.roomid, 'zhipu')
    return 1

async def zhipu_video(record: any):
    text = record.content
    match = re.search(r'^zp+(.*)', text)
    if match:
        prompt = match.group(1)
    else:
        send_remind('智谱视频出错，请联系管理员', record.roomid, 'zhipu')
        return 0 
    key = Config().get_config("zhipu_key")
    client = ZhipuAI(api_key=key)
    try:
        response = client.videos.generations(
            model="cogvideox",
            prompt=prompt,
        )
        while True:
            video = client.videos.retrieve_videos_result(
                id=response.id
                )
            print(video)
            if video.task_status == "SUCCESS":
                mp4_url = video.video_result[0].url
                # print(mp4_url)
                break
            else:
                await asyncio.sleep(10)
        send_remind(mp4_url, record.roomid, 'zhipu')
        return mp4_url
    except Exception as e:
        send_remind(str(e), record.roomid, 'zhipu')
        return str(e)
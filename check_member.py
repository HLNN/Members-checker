import os
import argparse
import base64
import json
from copy import deepcopy

import requests
import pyperclip
import cv2
from PIL import Image, ImageFont, ImageDraw
import numpy as np

import config


def get_token(ak=config.ak, sk=config.sk, token_file='token'):
    if os.path.exists(token_file):
        # TODO: check expiration
        with open(token_file, 'r') as f:
            token = f.read()
    else:
        host = f'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={ak}&client_secret={sk}'
        response = requests.get(host)
        if response:
            token = response.json()['access_token']
            with open(token_file, 'w') as f:
                f.write(token)

    return token


def load_txt(path):
    print(f'Loading members list from {path}...')
    with open(path, 'r', encoding='UTF-8') as f:
        members = f.read().split()
    print(members)
    print(f'{"*" * 20}\n')
    return members


def ocr(path):
    # request_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
    request_url = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate"

    print(f'Loading group members img from {path}...')
    with open(path, 'rb') as f:
        img_b64 = base64.b64encode(f.read())

    params = {"image": img_b64}
    access_token = get_token()
    request_url = request_url + "?access_token=" + access_token
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    response = requests.post(request_url, data=params, headers=headers)
    if response:
        print(f'Get ocr result:')
        # result = [{'words': w['words']} for w in response.json()['words_result']]
        result = response.json()['words_result']
        print([w['words'] for w in result])
        print(f'{"*" * 20}\n')
        return result


def match(txt, ocr):
    '''
    Auto match TXT member list with OCR member list
    :param txt: member list load from .txt file
    :param ocr: member list from screenshot img
    :return: match result, in or out of group
    '''
    ocr = [m['words'] for m in ocr]
    result= []
    for m in txt:
        result.append('' if m in ocr else 'no')

    result.append('Group member not in list')
    for m in ocr:
        if m not in txt:
            result.append(m)

    return result


def check_ocr(txt, ocr, img, font):
    '''
    Manually correct wrong OCR results with visual aid
    :param txt: member list load from .txt file
    :param ocr: member list from screenshot img
    :param img: raw group members screenshot img
    :param font: font object for chinese display
    :return:
    '''
    win_name = 'Img'
    i = 0
    while i < len(ocr):
        m = ocr[i]
        if m['words'] in txt:
            print(f'[{m["words"]}] in member list')
            i += 1
        else:
            location = m['location']
            pt1 = (location['left'], location['top'])
            pt2 = (location['left'] + location['width'], location['top'] + location['height'])
            pt3 = (location['left'], location['top'] + location['height'])
            img_rect = img.copy()
            cv2.rectangle(img_rect, pt1, pt2, (0, 255, 0), 3)
            # cv2.putText(img_rect, m['words'], pt3, cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
            img_pil = Image.fromarray(img_rect)
            draw = ImageDraw.Draw(img_pil)
            draw.text(pt3, m['words'], (255, 255, 255), font)
            img_rect = np.array(img_pil)
            base = max(0, location['top'] - 300)
            img_rect = img_rect[base:, :]

            pyperclip.copy(m['words'])
            single_command = 'dk'
            param_command = 'rs'

            def command_input(name):
                command, param = '', []
                s = f'[{name}] not in member list, d:delete, r:rename, s:split, k:keep...\n'
                while not (command and (command in single_command or command in param_command and param)):
                    cv2.imshow(win_name, img_rect)
                    cv2.waitKey(1)
                    command_str = input(s)
                    command_split = command_str.split(':')
                    if len(command_split) > 1:
                        command, param = command_split
                    else:
                        command = command_split[0]
                    s = f'Wrong input command, d:delete, r:rename, s:split, k:keep...\n'
                return command, param

            command, param = command_input(m['words'])

            if command == 'd':
                del(ocr[i])
            elif command == 'r':
                ocr[i]['words'] = param
            elif command == 's':
                def copy_item(w):
                    item = deepcopy(ocr[i])
                    item['words'] = w
                    return item

                param_list = param.split(' ')
                item_list = list(map(copy_item, param_list))
                ocr = ocr[:i] + item_list + ocr[i+1:]
            elif command == 'k':
                i += 1


def save_result(result, path):
    with open(path, 'w', encoding='UTF-8') as f:
        f.write('\n'.join(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check members in wechat group')
    parser.add_argument('--dir', default='', help='path to config file', type=str)
    args = parser.parse_args()

    assert args.dir != '', 'No dir path!'

    txt_path = os.path.join(args.dir, 'member.txt')
    assert os.path.exists(txt_path), 'No txt file found!'

    img_path = os.path.join(args.dir, 'member.png')
    if not os.path.exists(img_path):
        img_path = os.path.join(args.dir, 'member.jpg')
    assert os.path.exists(img_path), 'No img file found!'

    members_txt = load_txt(txt_path)
    members_ocr = ocr(img_path)

    img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), -1)
    font = ImageFont.truetype('./simsun.ttc', 30)

    check_ocr(members_txt, members_ocr, img, font)
    check_result = match(members_txt, members_ocr)

    save_path = txt_path[:-4] + '_check.txt'
    save_result(check_result, save_path)

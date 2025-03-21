# _*_ coding: utf-8 _*_
# @Time: 2024/09/23 11:31
# @Author: Tech_T

import yaml
import os


class Config:
    def __init__(self):
        self.root_path = os.path.dirname(__file__)
        self.config_path = self.root_path +'/config.yaml'
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

    def get_config(self, key):
        return self.config[key]
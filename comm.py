#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python版本的HTTP/3服务器，兼容Go版本的client
"""

import asyncio
import json
import logging
import math
import os
import signal
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Any

# 使用Hypercorn作为HTTP/3服务器
# 需要安装: pip install hypercorn quart httpx
from quart import Quart, request, jsonify
from hypercorn.asyncio import serve
from hypercorn.config import Config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建Quart应用实例
app = Quart(__name__)

# 使用线程锁保护的字典来模拟数据存储
mock_data_store = {}
mock_data_lock = threading.Lock()


class Data:
    """数据结构类，对应Go中的Data结构体"""
    def __init__(self, **kwargs):
        self.Name: str = kwargs.get('Name', '')
        self.IP: str = kwargs.get('IP', '')
        self.Port: int = kwargs.get('Port', 0)
        self.X: float = kwargs.get('X', 0.0)
        self.Y: float = kwargs.get('Y', 0.0)
        self.Psi: float = kwargs.get('Psi', 0.0)
        self.Stop_label: bool = kwargs.get('Stop_label', False)
        self.Req_Resp: bool = kwargs.get('Req_Resp', False)
        self.V: float = kwargs.get('V', 0.0)
        self.W: float = kwargs.get('W', 0.0)
        self.Path_Param: List[float] = kwargs.get('Path_Param', [])
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'Name': self.Name,
            'IP': self.IP,
            'Port': self.Port,
            'X': self.X,
            'Y': self.Y,
            'Psi': self.Psi,
            'Stop_label': self.Stop_label,
            'Req_Resp': self.Req_Resp,
            'V': self.V,
            'W': self.W,
            'Path_Param': self.Path_Param
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Data':
        """从字典创建实例"""
        return cls(**data)


def generate_straight_path(current_x: float, current_y: float, heading: float, point_count: int) -> List[float]:
    """根据当前位置、朝向生成向斜前方的直线轨迹
    
    参数:
        current_x, current_y: 当前位置坐标
        heading: 车辆朝向（弧度制，0度为x轴正方向）
        point_count: 需要生成的轨迹点数量
    
    返回:
        格式为 [X1, Y1, X2, Y2, ...] 的轨迹点列表，每个点占两个元素
    """
    # 创建轨迹点列表，每个点需要2个float值（X和Y）
    path = [0.0] * (point_count * 2)
    
    # 设置起始点为当前位置
    path[0] = current_x
    path[1] = current_y
    
    # 计算每个点之间的步长，使用固定步长使轨迹呈直线
    step_size = 1.0  # 可以根据需要调整步长
    
    # 从第二个点开始计算
    for i in range(1, point_count):
        # 计算沿朝向方向的偏移量
        step_distance = float(i) * step_size
        
        # 根据朝向计算新点的坐标
        # 朝向为0度时，车辆朝向x轴正方向
        # 角度增加时，逆时针旋转
        x_offset = step_distance * math.cos(heading)
        y_offset = step_distance * math.sin(heading)
        
        # 设置轨迹点
        path[2 * i] = current_x + x_offset
        path[2 * i + 1] = current_y + y_offset
    
    return path


@app.route('/', methods=['GET'])
async def root_handler():
    """根路径处理函数"""
    logger.info(f"Root request: {request}")
    # 获取URL路径中的数字
    path = request.path.lstrip('/')
    if path and path.isdigit():
        num = int(path)
        if 0 < num <= 1024 * 1024 * 1024:  # 限制最大1GB
            # 生成伪随机数据
            # 这里简化处理，返回一些数据
            return b'0' * min(num, 1024)  # 限制返回大小防止内存问题
    
    return '', 400


@app.route('/demo/hash', methods=['POST'])
async def hash_handler():
    """/demo/hash路径处理函数"""
    try:
        # 解析请求体中的JSON数据
        request_data = await request.get_json()
        message = Data.from_dict(request_data)
        
        logger.info(f"Message X: {message.X}")
        
        # 模拟存储数据
        logger.info("Storing data in mock store:")
        for key, value in message.to_dict().items():
            logger.info(f"Field '{key}': {value}")
        
        # 模拟返回数据
        response = message
        response.V = 1.0
        response.W = 0.5
        
        # 返回相同的JSON数据
        return jsonify(response.to_dict())
    
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON: {e}")
        return {'error': 'Invalid JSON data'}, 400
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return {'error': 'Internal server error'}, 500


@app.route('/demo/string', methods=['POST'])
async def string_handler():
    """/demo/string路径处理函数"""
    try:
        # 读取请求体
        body_bytes = await request.get_data()
        body_string = body_bytes.decode('utf-8')
        
        # 解析JSON数据
        body_data_dict = json.loads(body_string)
        body_data = Data.from_dict(body_data_dict)
        
        logger.info(f"Req from: {body_data.Name}")
        
        # 模拟在clouder_list中增加对象
        logger.info(f"Processing request from: {body_data.Name}")
        
        # 线程安全地访问模拟数据存储
        with mock_data_lock:
            # 检查是否已存在
            list_key = "clouder_list"
            if list_key in mock_data_store:
                if isinstance(mock_data_store[list_key], dict):
                    if body_data.Name not in mock_data_store[list_key]:
                        mock_data_store[list_key][body_data.Name] = True
                        logger.info(f"Add '{body_data.Name}' to clouder_list")
            else:
                # 创建新的列表
                mock_data_store[list_key] = {body_data.Name: True}
                logger.info(f"Add '{body_data.Name}' to clouder_list")
            
            # 模拟将请求body字符串存入存储
            mock_data_store[body_data.Name] = body_string
            logger.info(f"Request Body: {body_string}")
            
            # 模拟获取键"carX-c"command的值
            command_key = f"{body_data.Name}-c"
            carcommand_data = None
            exists = False
            
            if command_key in mock_data_store:
                exists = True
                carcommand_data = mock_data_store[command_key]
            else:
                # 如果键不存在，设置键值
                mock_data_store[command_key] = body_string
                logger.info(f"{body_data.Name} First connection")
            
        # 处理轨迹生成逻辑
        # 首先解析响应数据到结构体
        if exists and carcommand_data:
            command_data_dict = json.loads(carcommand_data)
            response = Data.from_dict(command_data_dict)
            
            # 检查Req_Resp是否为true，将其重置为false
            if response.Req_Resp:
                logger.info(f"Command: {carcommand_data}")
                response.Req_Resp = False
                
                # 将更新后的值存回模拟存储
                with mock_data_lock:
                    mock_data_store[command_key] = json.dumps(response.to_dict())
        else:
            response = body_data  # 如果没有存储的命令，使用请求数据
        
        # 生成轨迹点：从当前位置向斜前方延伸的直线
        response.Path_Param = generate_straight_path(body_data.X, body_data.Y, body_data.Psi, 20)
        
        # 记录生成的轨迹信息
        logger.info(f"Generated path with {len(response.Path_Param) // 2} points, "
                    f"starting at ({body_data.X:.2f}, {body_data.Y:.2f}), "
                    f"direction: {body_data.Psi:.2f} radians")
        
        # 返回JSON响应
        return jsonify(response.to_dict())
    
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON: {e}")
        return {'error': 'Invalid JSON data'}, 400
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return {'error': 'Internal server error'}, 500


def handle_shutdown(signum, frame):
    """处理系统信号，优雅关闭服务器"""
    logger.info(f"Received signal {signum}. Shutting down...")
    # 清理模拟数据存储
    with mock_data_lock:
        mock_data_store.clear()
    logger.info("Mock data store cleared")
    sys.exit(0)


async def main():
    """主函数"""
    # 设置信号处理
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # 配置Hypercorn服务器
    config = Config()
    config.bind = ['0.0.0.0:6121']  # 绑定到与Go版本相同的端口
    config.certfile = 'certpath/cert.pem'  # TLS证书文件
    config.keyfile = 'certpath/priv.key'   # TLS私钥文件
    config.http3 = True   # 启用HTTP/3
    config.h11 = True     # 启用HTTP/1.1
    config.h2 = True      # 启用HTTP/2
    config.loglevel = 'DEBUG'  # 设置日志级别为DEBUG
    config.keep_alive_timeout = 30  # 增加保活超时
    config.worker_class = 'asyncio'  # 使用asyncio工作器类
    
    # 检查证书文件是否存在
    if not os.path.exists(config.certfile):
        logger.error(f"Certificate file not found: {config.certfile}")
        sys.exit(1)
    if not os.path.exists(config.keyfile):
        logger.error(f"Key file not found: {config.keyfile}")
        sys.exit(1)
    
    logger.info(f"Starting multi-protocol server on {config.bind}")
    logger.info(f"Using certfile: {config.certfile}")
    logger.info(f"Using keyfile: {config.keyfile}")
    logger.info("HTTP/1.1 enabled: True")
    logger.info("HTTP/2 enabled: True")
    logger.info("HTTP/3 enabled: True")
    logger.info("Server will automatically negotiate protocol with clients")
    logger.info("Waiting for client connections...")
    
    try:
        await serve(app, config)
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, exiting...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
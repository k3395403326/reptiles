"""
监控和控制系统

提供实时状态监控、错误阈值检测和控制接口。
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from enum import Enum

from .models import ScraperConfig


logger = logging.getLogger(__name__)


class ScraperState(Enum):
    """爬虫状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class MonitorManager:
    """监控管理器"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        
        # 状态
        self.state = ScraperState.IDLE
        self.start_time: Optional[datetime] = None
        self.pause_time: Optional[datetime] = None
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_videos': 0,
            'successful_videos': 0,
            'failed_videos': 0,
            'errors': [],
            'warnings': []
        }
        
        # 性能指标
        self.performance = {
            'avg_response_time': 0.0,
            'requests_per_minute': 0.0,
            'memory_usage': 0,
            'response_times': []
        }
        
        # 错误阈值
        self.error_threshold = self.config.error_threshold
        self.consecutive_errors = 0
        
        # 回调函数
        self.on_error_threshold: Optional[Callable[[], None]] = None
        self.on_state_change: Optional[Callable[[ScraperState], None]] = None
    
    def start(self):
        """开始监控"""
        self.state = ScraperState.RUNNING
        self.start_time = datetime.now()
        self.consecutive_errors = 0
        
        logger.info("监控已启动")
        
        if self.on_state_change:
            self.on_state_change(self.state)
    
    def pause(self):
        """暂停监控"""
        if self.state == ScraperState.RUNNING:
            self.state = ScraperState.PAUSED
            self.pause_time = datetime.now()
            
            logger.info("监控已暂停")
            
            if self.on_state_change:
                self.on_state_change(self.state)
    
    def resume(self):
        """恢复监控"""
        if self.state == ScraperState.PAUSED:
            self.state = ScraperState.RUNNING
            self.pause_time = None
            
            logger.info("监控已恢复")
            
            if self.on_state_change:
                self.on_state_change(self.state)
    
    def stop(self):
        """停止监控"""
        self.state = ScraperState.STOPPED
        
        logger.info("监控已停止")
        
        if self.on_state_change:
            self.on_state_change(self.state)
    
    def record_request(self, success: bool, response_time: float = 0.0):
        """
        记录请求
        
        Args:
            success: 是否成功
            response_time: 响应时间
        """
        self.stats['total_requests'] += 1
        
        if success:
            self.stats['successful_requests'] += 1
            self.consecutive_errors = 0
        else:
            self.stats['failed_requests'] += 1
            self.consecutive_errors += 1
            
            # 检查错误阈值
            self._check_error_threshold()
        
        # 记录响应时间
        if response_time > 0:
            self.performance['response_times'].append(response_time)
            # 只保留最近100个响应时间
            if len(self.performance['response_times']) > 100:
                self.performance['response_times'] = self.performance['response_times'][-100:]
            
            # 更新平均响应时间
            self.performance['avg_response_time'] = sum(self.performance['response_times']) / len(self.performance['response_times'])
    
    def record_video(self, success: bool, error_message: str = None):
        """
        记录视频处理
        
        Args:
            success: 是否成功
            error_message: 错误信息
        """
        self.stats['total_videos'] += 1
        
        if success:
            self.stats['successful_videos'] += 1
        else:
            self.stats['failed_videos'] += 1
            if error_message:
                self.stats['errors'].append({
                    'timestamp': datetime.now().isoformat(),
                    'message': error_message
                })
    
    def record_error(self, error: Exception, context: Dict[str, Any] = None):
        """
        记录错误
        
        Args:
            error: 异常对象
            context: 上下文信息
        """
        error_info = {
            'timestamp': datetime.now().isoformat(),
            'type': type(error).__name__,
            'message': str(error),
            'context': context or {}
        }
        
        self.stats['errors'].append(error_info)
        
        # 只保留最近50个错误
        if len(self.stats['errors']) > 50:
            self.stats['errors'] = self.stats['errors'][-50:]
        
        self.consecutive_errors += 1
        self._check_error_threshold()
    
    def record_warning(self, message: str):
        """
        记录警告
        
        Args:
            message: 警告信息
        """
        warning_info = {
            'timestamp': datetime.now().isoformat(),
            'message': message
        }
        
        self.stats['warnings'].append(warning_info)
        
        # 只保留最近50个警告
        if len(self.stats['warnings']) > 50:
            self.stats['warnings'] = self.stats['warnings'][-50:]
    
    def _check_error_threshold(self):
        """检查错误阈值"""
        if self.consecutive_errors >= self.error_threshold:
            logger.warning(f"连续错误达到阈值: {self.consecutive_errors}")
            
            # 自动暂停
            self.state = ScraperState.ERROR
            
            if self.on_error_threshold:
                self.on_error_threshold()
            
            if self.on_state_change:
                self.on_state_change(self.state)
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        total = self.stats['total_requests']
        if total == 0:
            return 0.0
        return self.stats['successful_requests'] / total
    
    def get_video_success_rate(self) -> float:
        """获取视频处理成功率"""
        total = self.stats['total_videos']
        if total == 0:
            return 0.0
        return self.stats['successful_videos'] / total
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            'state': self.state.value,
            'uptime': uptime,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'stats': self.stats.copy(),
            'performance': {
                'avg_response_time': self.performance['avg_response_time'],
                'requests_per_minute': self._calculate_rpm()
            },
            'success_rate': self.get_success_rate(),
            'video_success_rate': self.get_video_success_rate(),
            'consecutive_errors': self.consecutive_errors,
            'error_threshold': self.error_threshold
        }
    
    def _calculate_rpm(self) -> float:
        """计算每分钟请求数"""
        if not self.start_time:
            return 0.0
        
        uptime_minutes = (datetime.now() - self.start_time).total_seconds() / 60
        if uptime_minutes == 0:
            return 0.0
        
        return self.stats['total_requests'] / uptime_minutes
    
    def reset(self):
        """重置监控数据"""
        self.state = ScraperState.IDLE
        self.start_time = None
        self.pause_time = None
        self.consecutive_errors = 0
        
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_videos': 0,
            'successful_videos': 0,
            'failed_videos': 0,
            'errors': [],
            'warnings': []
        }
        
        self.performance = {
            'avg_response_time': 0.0,
            'requests_per_minute': 0.0,
            'memory_usage': 0,
            'response_times': []
        }
        
        logger.info("监控数据已重置")


class ControlManager:
    """控制管理器"""
    
    def __init__(self, monitor: MonitorManager):
        self.monitor = monitor
        self._pause_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._pause_event.set()  # 初始状态为非暂停
        
        # 命令队列
        self.command_queue: List[Dict[str, Any]] = []
    
    async def pause(self) -> bool:
        """
        暂停爬虫
        
        Returns:
            bool: 是否成功
        """
        if self.monitor.state == ScraperState.RUNNING:
            self._pause_event.clear()
            self.monitor.pause()
            logger.info("爬虫已暂停")
            return True
        return False
    
    async def resume(self) -> bool:
        """
        恢复爬虫
        
        Returns:
            bool: 是否成功
        """
        if self.monitor.state == ScraperState.PAUSED:
            self._pause_event.set()
            self.monitor.resume()
            logger.info("爬虫已恢复")
            return True
        return False
    
    async def stop(self) -> bool:
        """
        停止爬虫
        
        Returns:
            bool: 是否成功
        """
        self._stop_event.set()
        self._pause_event.set()  # 确保不会卡在暂停状态
        self.monitor.stop()
        logger.info("爬虫已停止")
        return True
    
    async def wait_if_paused(self):
        """等待如果处于暂停状态"""
        await self._pause_event.wait()
    
    def is_stopped(self) -> bool:
        """检查是否已停止"""
        return self._stop_event.is_set()
    
    def is_paused(self) -> bool:
        """检查是否已暂停"""
        return not self._pause_event.is_set()
    
    async def graceful_shutdown(self, timeout: float = 30.0) -> bool:
        """
        优雅关闭
        
        Args:
            timeout: 超时时间
            
        Returns:
            bool: 是否成功
        """
        logger.info("开始优雅关闭...")
        
        # 设置停止标志
        self._stop_event.set()
        self._pause_event.set()
        
        # 等待当前任务完成
        try:
            await asyncio.wait_for(self._wait_for_completion(), timeout)
            logger.info("优雅关闭完成")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"优雅关闭超时 ({timeout}s)")
            return False
    
    async def _wait_for_completion(self):
        """等待当前任务完成"""
        # 这里可以添加等待逻辑
        await asyncio.sleep(0.1)
    
    def send_command(self, command: str, params: Dict[str, Any] = None):
        """
        发送控制命令
        
        Args:
            command: 命令名称
            params: 命令参数
        """
        self.command_queue.append({
            'command': command,
            'params': params or {},
            'timestamp': datetime.now().isoformat()
        })
    
    async def process_commands(self):
        """处理命令队列"""
        while self.command_queue:
            cmd = self.command_queue.pop(0)
            
            command = cmd['command']
            params = cmd['params']
            
            if command == 'pause':
                await self.pause()
            elif command == 'resume':
                await self.resume()
            elif command == 'stop':
                await self.stop()
            elif command == 'update_config':
                # 更新配置
                pass
            else:
                logger.warning(f"未知命令: {command}")
    
    def reset(self):
        """重置控制器"""
        self._pause_event.set()
        self._stop_event.clear()
        self.command_queue.clear()
        logger.info("控制器已重置")
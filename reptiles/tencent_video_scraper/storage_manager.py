"""
存储管理器

处理数据保存，支持多种输出格式（JSON、CSV、XML）。
"""

import json
import csv
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .models import VideoData, BatchReport, ScraperConfig


logger = logging.getLogger(__name__)


class StorageManager:
    """存储管理器"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.output_dir = self.config.download_path
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 统计信息
        self.stats = {
            'files_saved': 0,
            'total_bytes': 0,
            'save_errors': 0
        }
    
    def save_video_data(self, video_data: VideoData, filename: Optional[str] = None) -> str:
        """
        保存视频数据
        
        Args:
            video_data: 视频数据
            filename: 文件名（可选）
            
        Returns:
            str: 保存的文件路径
        """
        if not filename:
            # 生成文件名
            safe_title = self._sanitize_filename(video_data.title)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_title}_{timestamp}"
        
        output_format = self.config.output_format.lower()
        
        if output_format == 'json':
            return self._save_as_json(video_data, filename)
        elif output_format == 'csv':
            return self._save_as_csv([video_data], filename)
        elif output_format == 'xml':
            return self._save_as_xml(video_data, filename)
        else:
            logger.warning(f"不支持的输出格式: {output_format}，使用JSON")
            return self._save_as_json(video_data, filename)
    
    def save_batch_data(self, videos: List[VideoData], filename: Optional[str] = None) -> str:
        """
        批量保存视频数据
        
        Args:
            videos: 视频数据列表
            filename: 文件名（可选）
            
        Returns:
            str: 保存的文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"batch_{timestamp}"
        
        output_format = self.config.output_format.lower()
        
        if output_format == 'json':
            return self._save_batch_as_json(videos, filename)
        elif output_format == 'csv':
            return self._save_as_csv(videos, filename)
        elif output_format == 'xml':
            return self._save_batch_as_xml(videos, filename)
        else:
            logger.warning(f"不支持的输出格式: {output_format}，使用JSON")
            return self._save_batch_as_json(videos, filename)
    
    def save_batch_report(self, report: BatchReport, filename: Optional[str] = None) -> str:
        """
        保存批量任务报告
        
        Args:
            report: 批量报告
            filename: 文件名（可选）
            
        Returns:
            str: 保存的文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{timestamp}"
        
        filepath = os.path.join(self.output_dir, f"{filename}.json")
        
        try:
            report_dict = report.to_dict()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report_dict, f, ensure_ascii=False, indent=2)
            
            self.stats['files_saved'] += 1
            self.stats['total_bytes'] += os.path.getsize(filepath)
            
            logger.info(f"批量报告已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.stats['save_errors'] += 1
            logger.error(f"保存批量报告失败: {e}")
            raise
    
    def _save_as_json(self, video_data: VideoData, filename: str) -> str:
        """保存为JSON格式"""
        filepath = os.path.join(self.output_dir, f"{filename}.json")
        
        try:
            data_dict = video_data.to_dict()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_dict, f, ensure_ascii=False, indent=2)
            
            self.stats['files_saved'] += 1
            self.stats['total_bytes'] += os.path.getsize(filepath)
            
            logger.info(f"视频数据已保存为JSON: {filepath}")
            return filepath
            
        except Exception as e:
            self.stats['save_errors'] += 1
            logger.error(f"保存JSON失败: {e}")
            raise
    
    def _save_batch_as_json(self, videos: List[VideoData], filename: str) -> str:
        """批量保存为JSON格式"""
        filepath = os.path.join(self.output_dir, f"{filename}.json")
        
        try:
            data_list = [video.to_dict() for video in videos]
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_list, f, ensure_ascii=False, indent=2)
            
            self.stats['files_saved'] += 1
            self.stats['total_bytes'] += os.path.getsize(filepath)
            
            logger.info(f"批量视频数据已保存为JSON: {filepath}")
            return filepath
            
        except Exception as e:
            self.stats['save_errors'] += 1
            logger.error(f"批量保存JSON失败: {e}")
            raise
    
    def _save_as_csv(self, videos: List[VideoData], filename: str) -> str:
        """保存为CSV格式"""
        filepath = os.path.join(self.output_dir, f"{filename}.csv")
        
        try:
            # 定义CSV列
            fieldnames = [
                'url', 'title', 'description', 'duration', 'view_count',
                'publish_time', 'is_svip', 'thumbnail_url', 'tags',
                'video_urls_count', 'comments_count'
            ]
            
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for video in videos:
                    row = {
                        'url': video.url,
                        'title': video.title,
                        'description': video.description[:200] if video.description else '',
                        'duration': video.duration,
                        'view_count': video.view_count,
                        'publish_time': video.publish_time.isoformat() if video.publish_time else '',
                        'is_svip': video.is_svip,
                        'thumbnail_url': video.thumbnail_url,
                        'tags': ','.join(video.tags) if video.tags else '',
                        'video_urls_count': len(video.video_urls),
                        'comments_count': len(video.comments)
                    }
                    writer.writerow(row)
            
            self.stats['files_saved'] += 1
            self.stats['total_bytes'] += os.path.getsize(filepath)
            
            logger.info(f"视频数据已保存为CSV: {filepath}")
            return filepath
            
        except Exception as e:
            self.stats['save_errors'] += 1
            logger.error(f"保存CSV失败: {e}")
            raise
    
    def _save_as_xml(self, video_data: VideoData, filename: str) -> str:
        """保存为XML格式"""
        filepath = os.path.join(self.output_dir, f"{filename}.xml")
        
        try:
            root = ET.Element('video')
            
            # 添加基本信息
            ET.SubElement(root, 'url').text = video_data.url
            ET.SubElement(root, 'title').text = video_data.title
            ET.SubElement(root, 'description').text = video_data.description
            ET.SubElement(root, 'duration').text = str(video_data.duration)
            ET.SubElement(root, 'view_count').text = str(video_data.view_count)
            ET.SubElement(root, 'publish_time').text = video_data.publish_time.isoformat() if video_data.publish_time else ''
            ET.SubElement(root, 'is_svip').text = str(video_data.is_svip).lower()
            ET.SubElement(root, 'thumbnail_url').text = video_data.thumbnail_url
            
            # 添加标签
            tags_elem = ET.SubElement(root, 'tags')
            for tag in video_data.tags:
                ET.SubElement(tags_elem, 'tag').text = tag
            
            # 添加视频链接
            urls_elem = ET.SubElement(root, 'video_urls')
            for video_url in video_data.video_urls:
                url_elem = ET.SubElement(urls_elem, 'video_url')
                ET.SubElement(url_elem, 'quality').text = video_url.quality
                ET.SubElement(url_elem, 'url').text = video_url.url
                ET.SubElement(url_elem, 'format').text = video_url.format
            
            # 格式化XML
            xml_str = minidom.parseString(ET.tostring(root, encoding='unicode')).toprettyxml(indent='  ')
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml_str)
            
            self.stats['files_saved'] += 1
            self.stats['total_bytes'] += os.path.getsize(filepath)
            
            logger.info(f"视频数据已保存为XML: {filepath}")
            return filepath
            
        except Exception as e:
            self.stats['save_errors'] += 1
            logger.error(f"保存XML失败: {e}")
            raise
    
    def _save_batch_as_xml(self, videos: List[VideoData], filename: str) -> str:
        """批量保存为XML格式"""
        filepath = os.path.join(self.output_dir, f"{filename}.xml")
        
        try:
            root = ET.Element('videos')
            root.set('count', str(len(videos)))
            
            for video_data in videos:
                video_elem = ET.SubElement(root, 'video')
                
                ET.SubElement(video_elem, 'url').text = video_data.url
                ET.SubElement(video_elem, 'title').text = video_data.title
                ET.SubElement(video_elem, 'duration').text = str(video_data.duration)
                ET.SubElement(video_elem, 'view_count').text = str(video_data.view_count)
                ET.SubElement(video_elem, 'is_svip').text = str(video_data.is_svip).lower()
            
            xml_str = minidom.parseString(ET.tostring(root, encoding='unicode')).toprettyxml(indent='  ')
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml_str)
            
            self.stats['files_saved'] += 1
            self.stats['total_bytes'] += os.path.getsize(filepath)
            
            logger.info(f"批量视频数据已保存为XML: {filepath}")
            return filepath
            
        except Exception as e:
            self.stats['save_errors'] += 1
            logger.error(f"批量保存XML失败: {e}")
            raise
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符"""
        # 移除非法字符
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        # 限制长度
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename.strip()
    
    def verify_file_integrity(self, filepath: str) -> bool:
        """
        验证文件完整性
        
        Args:
            filepath: 文件路径
            
        Returns:
            bool: 文件是否完整有效
        """
        try:
            if not os.path.exists(filepath):
                return False
            
            # 检查文件大小
            if os.path.getsize(filepath) == 0:
                return False
            
            # 根据文件类型验证
            ext = os.path.splitext(filepath)[1].lower()
            
            if ext == '.json':
                with open(filepath, 'r', encoding='utf-8') as f:
                    json.load(f)
                return True
                
            elif ext == '.csv':
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    # 至少有表头
                    header = next(reader, None)
                    return header is not None
                    
            elif ext == '.xml':
                ET.parse(filepath)
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"文件完整性验证失败: {filepath}, 错误: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'files_saved': 0,
            'total_bytes': 0,
            'save_errors': 0
        }
"""知识条目整理模块。

本模块提供对分析后的知识条目进行整理的功能，包括去重、格式标准化、
分类存储和元数据补充，生成最终的知识库条目。
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
import hashlib

# 配置日志
logger = logging.getLogger(__name__)


def read_analysis_results(file_path: str) -> List[Dict[str, Any]]:
    """读取分析结果文件。
    
    Args:
        file_path: JSON 文件路径，包含分析结果
        
    Returns:
        分析结果条目列表
        
    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 格式错误
        ValueError: 数据格式不符合预期
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            raise ValueError("分析结果应该是 JSON 数组")
            
        logger.info(f"成功读取 {len(data)} 条分析结果")
        return data
        
    except FileNotFoundError:
        logger.error(f"文件不存在: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析错误: {e}")
        raise
    except Exception as e:
        logger.error(f"读取分析结果时发生错误: {e}")
        raise


def deduplicate_by_url(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """基于 URL 去重，保留最新版本。
    
    Args:
        entries: 知识条目列表
        
    Returns:
        去重后的条目列表
    """
    seen_urls: Set[str] = set()
    unique_entries: List[Dict[str, Any]] = []
    
    # 按 collected_at 降序排序，确保保留最新的
    sorted_entries = sorted(
        entries,
        key=lambda x: x.get('collected_at', ''),
        reverse=True
    )
    
    for entry in sorted_entries:
        url = entry.get('url') or entry.get('source_url')
        if not url:
            logger.warning(f"条目缺少 URL: {entry.get('title', 'Unknown')}")
            unique_entries.append(entry)
            continue
            
        if url not in seen_urls:
            seen_urls.add(url)
            unique_entries.append(entry)
        else:
            logger.info(f"发现重复 URL，跳过: {url}")
    
    removed = len(entries) - len(unique_entries)
    if removed > 0:
        logger.info(f"URL 去重: 移除了 {removed} 个重复条目")
    
    return unique_entries


def generate_slug(title: str) -> str:
    """从标题生成 URL slug。
    
    Args:
        title: 文章或项目标题
        
    Returns:
        生成的 slug（小写字母、数字、连字符）
    """
    # 将标题转换为小写
    slug = title.lower()
    
    # 替换非字母数字字符为连字符
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    
    # 移除首尾连字符
    slug = slug.strip('-')
    
    # 限制长度
    if len(slug) > 50:
        # 保留前 50 个字符，但确保不在单词中间截断
        slug = slug[:50]
        if slug[-1] != '-':
            # 找到最后一个连字符
            last_hyphen = slug.rfind('-')
            if last_hyphen > 30:  # 确保至少保留一定长度
                slug = slug[:last_hyphen]
    
    return slug


def estimate_reading_time(content: str) -> str:
    """估算阅读时间。
    
    基于中文阅读速度约 300 字/分钟。
    
    Args:
        content: 内容文本
        
    Returns:
        "short" (1-3分钟), "medium" (4-7分钟), "long" (8+分钟)
    """
    if not content:
        return "short"
    
    # 估算中文字数（每个中文字符算一个字）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
    # 估算英文单词数（按空格分割）
    english_words = len(re.findall(r'\b[a-zA-Z]+\b', content))
    
    # 总字数估算（英文单词按 1.5 字计算）
    total_words = chinese_chars + english_words * 1.5
    
    # 阅读时间估算（300 字/分钟）
    minutes = total_words / 300
    
    if minutes <= 3:
        return "short"
    elif minutes <= 7:
        return "medium"
    else:
        return "long"


def assess_technical_level(entry: Dict[str, Any]) -> str:
    """评估技术难度等级。
    
    Args:
        entry: 知识条目
        
    Returns:
        "beginner", "intermediate", 或 "advanced"
    """
    # 优先使用 metadata 中已有的 technical_level
    metadata = entry.get('metadata', {})
    if 'technical_level' in metadata:
        level = metadata['technical_level']
        if level in ['beginner', 'intermediate', 'advanced']:
            return level
    
    # 基于内容关键词启发式判断
    content = (entry.get('content', '') + ' ' + entry.get('summary', '')).lower()
    tags = [tag.lower() for tag in entry.get('tags', [])]
    
    advanced_keywords = [
        'architecture', 'optimization', 'algorithm', 'distributed',
        'concurrent', 'parallel', 'scalability', 'performance',
        'research', 'paper', 'theorem', 'proof', 'mathematical'
    ]
    
    beginner_keywords = [
        'tutorial', 'guide', 'introduction', 'getting started',
        'basic', 'fundamental', 'explained', 'simplified'
    ]
    
    # 检查高级关键词
    for keyword in advanced_keywords:
        if keyword in content:
            return 'advanced'
    
    # 检查初学者关键词
    for keyword in beginner_keywords:
        if keyword in content:
            return 'beginner'
    
    # 默认中级
    return 'intermediate'


def determine_audience(entry: Dict[str, Any]) -> List[str]:
    """确定目标读者群体。
    
    Args:
        entry: 知识条目
        
    Returns:
        读者群体列表，如 ["beginner", "developer", "researcher"]
    """
    audiences = []
    tags = [tag.lower() for tag in entry.get('tags', [])]
    category = entry.get('category', '').lower()
    
    # 基于标签和类别判断
    if 'research' in tags or category == 'paper':
        audiences.append('researcher')
    
    if 'framework' in tags or 'library' in tags or 'tool' in tags:
        audiences.append('developer')
    
    if 'tutorial' in tags or 'guide' in tags:
        audiences.append('beginner')
    
    # 基于技术难度
    tech_level = assess_technical_level(entry)
    if tech_level == 'beginner':
        audiences.append('beginner')
    elif tech_level == 'advanced':
        audiences.append('researcher')
        audiences.append('developer')
    else:  # intermediate
        audiences.append('developer')
    
    # 去重
    return list(dict.fromkeys(audiences))


def enhance_metadata(entry: Dict[str, Any]) -> Dict[str, Any]:
    """补充元数据。
    
    Args:
        entry: 原始知识条目
        
    Returns:
        补充了元数据的条目
    """
    metadata = entry.get('metadata', {})
    
    # 技术难度评估
    if 'technical_level' not in metadata:
        metadata['technical_level'] = assess_technical_level(entry)
    
    # 阅读时间估算
    content = entry.get('content', '') + ' ' + entry.get('summary', '')
    metadata['reading_time'] = estimate_reading_time(content)
    
    # 读者群体
    metadata['audience'] = determine_audience(entry)
    
    # 相似文章（暂时为空，需要更复杂的推荐系统）
    if 'similar_articles' not in metadata:
        metadata['similar_articles'] = []
    
    return metadata


def normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """标准化知识条目格式。
    
    Args:
        entry: 原始分析结果条目
        
    Returns:
        标准化后的知识条目
    """
    normalized = entry.copy()
    
    # 确保必要字段存在
    if 'id' not in normalized or not normalized['id']:
        normalized['id'] = str(uuid.uuid4())
    
    # 统一字段名称
    if 'url' in normalized and 'source_url' not in normalized:
        normalized['source_url'] = normalized['url']
    
    # 确保时间戳格式
    now = datetime.now(timezone.utc).isoformat()
    normalized['organized_at'] = now
    
    # 更新状态
    normalized['status'] = 'curated'
    
    # 补充元数据
    normalized['metadata'] = enhance_metadata(normalized)
    
    # 添加分发字段
    if 'distribution' not in normalized:
        normalized['distribution'] = {
            'telegram': {'sent_at': None, 'message_id': None},
            'feishu': {'sent_at': None, 'message_id': None}
        }
    
    # 清理可选字段
    optional_fields = ['score', 'score_reason']
    for field in optional_fields:
        if field in normalized and not normalized[field]:
            del normalized[field]
    
    return normalized


def generate_filename(entry: Dict[str, Any], date_str: str) -> str:
    """生成文件名。
    
    格式: {date}-{source}-{slug}.json
    
    Args:
        entry: 知识条目
        date_str: YYYY-MM-DD 格式的日期
        
    Returns:
        文件名
    """
    # 来源缩写
    source = entry.get('source', '').lower()
    if 'github' in source:
        source_abbr = 'gh'
    elif 'hacker' in source:
        source_abbr = 'hn'
    else:
        source_abbr = 'mix'
    
    # 生成 slug
    title = entry.get('title', 'untitled')
    slug = generate_slug(title)
    
    return f"{date_str}-{source_abbr}-{slug}.json"


def save_organized_entry(
    entry: Dict[str, Any],
    output_dir: str,
    date_str: str
) -> str:
    """保存整理后的知识条目。
    
    Args:
        entry: 整理后的知识条目
        output_dir: 输出目录
        date_str: YYYY-MM-DD 格式的日期
        
    Returns:
        保存的文件路径
    """
    # 创建月度目录 (YYYY-MM)
    year_month = date_str[:7]  # YYYY-MM
    month_dir = os.path.join(output_dir, year_month)
    os.makedirs(month_dir, exist_ok=True)
    
    # 生成文件名
    filename = generate_filename(entry, date_str)
    filepath = os.path.join(month_dir, filename)
    
    # 检查文件是否已存在
    if os.path.exists(filepath):
        logger.warning(f"文件已存在，将被覆盖: {filepath}")
    
    # 保存为 JSON
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    
    logger.info(f"已保存: {filepath}")
    return filepath


def organize_entries(
    entries: List[Dict[str, Any]],
    output_dir: str,
    date_str: Optional[str] = None
) -> Dict[str, Any]:
    """整理知识条目主函数。
    
    Args:
        entries: 分析结果条目列表
        output_dir: 输出目录
        date_str: 日期字符串 (YYYY-MM-DD)，默认为今天
        
    Returns:
        处理统计信息
    """
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 验证输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 去重
    unique_entries = deduplicate_by_url(entries)
    
    # 标准化
    organized_entries = []
    for entry in unique_entries:
        try:
            organized = normalize_entry(entry)
            organized_entries.append(organized)
        except Exception as e:
            logger.error(f"标准化条目失败: {entry.get('title', 'Unknown')} - {e}")
    
    # 保存
    saved_files = []
    for entry in organized_entries:
        try:
            filepath = save_organized_entry(entry, output_dir, date_str)
            saved_files.append(filepath)
        except Exception as e:
            logger.error(f"保存条目失败: {entry.get('title', 'Unknown')} - {e}")
    
    # 统计信息
    stats = {
        'total_input': len(entries),
        'after_deduplication': len(unique_entries),
        'successfully_organized': len(organized_entries),
        'successfully_saved': len(saved_files),
        'saved_files': saved_files,
        'date': date_str,
        'output_dir': output_dir
    }
    
    logger.info(f"整理完成: 输入 {stats['total_input']} 条, "
                f"去重后 {stats['after_deduplication']} 条, "
                f"整理成功 {stats['successfully_organized']} 条, "
                f"保存 {stats['successfully_saved']} 条")
    
    return stats


def organize_from_file(
    input_file: str,
    output_dir: str,
    date_str: Optional[str] = None
) -> Dict[str, Any]:
    """从文件读取分析结果并进行整理。
    
    Args:
        input_file: 输入文件路径（JSON）
        output_dir: 输出目录
        date_str: 日期字符串 (YYYY-MM-DD)，默认为今天
        
    Returns:
        处理统计信息
    """
    # 读取分析结果
    entries = read_analysis_results(input_file)
    
    # 整理
    stats = organize_entries(entries, output_dir, date_str)
    
    return stats


if __name__ == "__main__":
    # 示例用法
    import sys
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 默认参数
    input_file = "temp_analysis.json"
    output_dir = "knowledge/articles"
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    if len(sys.argv) > 3:
        date_str = sys.argv[3]
    
    try:
        stats = organize_from_file(input_file, output_dir, date_str)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        
        if stats['successfully_saved'] == 0:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"整理失败: {e}")
        sys.exit(1)
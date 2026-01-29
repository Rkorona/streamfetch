import subprocess
import logging
import os
from streamfetch.config.settings import config

logger = logging.getLogger("streamfetch")


def embed_metadata(audio_path, cover_path, lyrics_path, metadata, final_path):
    ffmpeg_bin = config["ffmpeg"]["binary"]

    # 基础命令: 输入音频
    args = [ffmpeg_bin, "-i", str(audio_path)]

    # 检查封面文件是否有效
    has_cover = False
    if cover_path and os.path.exists(cover_path) and os.path.getsize(cover_path) > 0:
        args.extend(["-i", str(cover_path)])
        has_cover = True

    # 映射音频流
    args.extend(["-map", "0:a"])

    # 如果有封面，映射视频流并标记为封面
    if has_cover:
        # -c:v mjpeg 确保封面被重新编码为兼容性最好的格式
        # -id3v2_version 3 提高 Windows 兼容性
        args.extend(["-map", "1", "-c:v", "mjpeg", "-disposition:v", "attached_pic"])

    # 写入元数据
    # 使用 -metadata:s:a:0 确保只写入音频流的标签
    args.extend(
        [
            "-metadata",
            f"title={metadata['title']}",
            "-metadata",
            f"artist={metadata['artist']}",
            "-metadata",
            f"album={metadata['album']}",
            "-metadata",
            f"track={metadata['trackNumber']}",
            "-metadata",
            "comment=Downloaded by StreamFetch",
        ]
    )

    # 嵌入歌词
    if lyrics_path and os.path.exists(lyrics_path):
        try:
            with open(lyrics_path, "r", encoding="utf-8") as f:
                lrc_content = f.read()
                args.extend(["-metadata", f"LYRICS={lrc_content}"])
        except Exception as e:
            logger.warning(f"读取歌词失败: {e}")

    # 输出文件参数
    # -c:a copy 表示音频流不重新编码（无损直通）
    args.extend(["-c:a", "copy", "-y", "-loglevel", "error", str(final_path)])

    try:
        subprocess.run(args, check=True)
    except FileNotFoundError:
        logger.error(f"找不到 FFmpeg，请检查配置文件中的路径: {ffmpeg_bin}")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg 混流失败: {e}")
        raise

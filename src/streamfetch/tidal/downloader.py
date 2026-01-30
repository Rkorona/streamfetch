import os
import random
import string
import logging
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamfetch.utils.http import fetch_get
from streamfetch.utils.filename import sanitize_filename, format_file_path
from streamfetch.dash.parser import DashParser
from streamfetch.media.ffmpeg import embed_metadata
from streamfetch.config.settings import config
from streamfetch.config.api_targets import get_base_url

logger = logging.getLogger("streamfetch")


class TidalDownloader:
    def __init__(self, api):
        self.api = api

    def _download_segment(self, url):
        try:
            return fetch_get(url).content
        except Exception as e:
            # logger.debug(f"分段下载失败 {url}: {e}")
            raise

    def download_dash(self, manifest_xml, output_path):
        parsed = DashParser.parse(manifest_xml)
        if not parsed:
            # 这里抛出异常，触发外层的重试逻辑
            raise Exception("DASH Manifest 解析失败 (API 返回了无效数据)")

        urls = DashParser.build_urls(parsed)
        total_segments = len(urls)

        if total_segments == 0:
            raise Exception("解析出的分段列表为空")

        downloaded_parts = {}
        max_workers = config["network"]["concurrency"]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self._download_segment, url): i
                for i, url in enumerate(urls)
            }

            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    data = future.result()
                    downloaded_parts[idx] = data
                except Exception as e:
                    raise Exception(f"分段 {idx} 下载失败: {e}")

        with open(output_path, "wb") as outfile:
            for i in range(total_segments):
                if i in downloaded_parts:
                    outfile.write(downloaded_parts[i])
                else:
                    raise Exception(f"缺失分段: {i}")

    def process_track(self, track_id, folder_path="."):
        folder_path = Path(folder_path)
        temp_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        temp_audio = folder_path / f"tmp_aud_{temp_id}.mp4"
        temp_cover = folder_path / f"tmp_cov_{temp_id}.jpg"
        temp_lyrics = folder_path / f"tmp_lyr_{temp_id}.txt"

        try:
            # 1. 获取元数据
            meta = self.api.get_metadata(track_id)
            safe_title = sanitize_filename(meta["title"])
            safe_artist = sanitize_filename(meta["artist"])
            file_template = config["naming"]["file_format"]
            final_path = format_file_path(
                file_template, meta, folder_path, extension=".flac"
            )
            filename_display = final_path.name
            if final_path.exists():
                logger.info(
                    f"⏭️  [yellow]跳过:[/yellow] {meta['title']} (已存在)",
                    extra={"markup": True},
                )
                return

            # 2. 确定音质顺序
            cfg_max_quality = config["audio"]["max_quality"]
            cfg_fallback = config["audio"]["auto_fallback"]

            quality_map = {
                "HI_RES": "HI_RES_LOSSLESS",
                "LOSSLESS": "LOSSLESS",
                "HIGH": "HIGH",
            }
            priority_list = ["HI_RES", "LOSSLESS", "HIGH"]

            try:
                user_limit_idx = priority_list.index(cfg_max_quality)
            except ValueError:
                user_limit_idx = 0

            song_max_quality = meta.get("audioQuality", "LOSSLESS")
            try:
                song_limit_idx = priority_list.index(song_max_quality)
            except ValueError:
                song_limit_idx = 1

            start_index = max(user_limit_idx, song_limit_idx)

            if cfg_fallback:
                qualities_to_try = priority_list[start_index:]
            else:
                qualities_to_try = [priority_list[start_index]]

            api_qualities = [quality_map[q] for q in qualities_to_try]
            download_success = False

            for quality in api_qualities:
                q_label = (
                    "Hi-Res"
                    if quality == "HI_RES_LOSSLESS"
                    else ("Lossless" if quality == "LOSSLESS" else "High")
                )
                max_retries = config["network"]["max_retries"]
                quality_success = False

                for attempt in range(1, max_retries + 1):
                    try:
                        if attempt == 1:
                            if len(api_qualities) > 1:
                                logger.info(
                                    f"🌐 尝试获取流: [cyan]{q_label}[/cyan]...",
                                    extra={"markup": True},
                                )
                            else:
                                logger.info(
                                    f"🌐 [cyan][3/6][/cyan] 获取流清单 ({q_label})...",
                                    extra={"markup": True},
                                )
                        else:
                            logger.info(
                                f"   🔄 [yellow]重试 ({attempt}/{
                                    max_retries
                                }):[/yellow] {q_label}...",
                                extra={"markup": True},
                            )

                        manifest = self.api.get_stream_manifest(track_id, quality)
                        self.download_dash(manifest, temp_audio)
                        quality_success = True
                        break

                    except Exception as e:
                        if "404" in str(e):
                            logger.debug(f"   -> {q_label} 不可用 (404)")
                            break

                        if attempt < max_retries:
                            logger.warning(f"   -> ⚠️  {q_label} 失败: {e}")

                            try:
                                new_base_url = get_base_url()
                                self.api.base_url = new_base_url
                                logger.info(
                                    f"   -> 🔌 [bold magenta]自动切换线路:[/bold magenta] {
                                        new_base_url
                                    }",
                                    extra={"markup": True},
                                )
                            except:
                                pass

                            time.sleep(1)  # 稍作等待
                        else:
                            logger.warning(f"   -> ❌ {q_label} 最终失败: {e}")

                if quality_success:
                    download_success = True
                    if len(api_qualities) > 1 and quality != api_qualities[0]:
                        logger.info(f"   -> ✅ 降级下载成功: {q_label}")
                    else:
                        logger.info(f"   -> ✅ {q_label} 下载成功")
                    break

            if not download_success:
                logger.error(
                    f"❌ [bold red]所有音质均下载失败[/bold red]: {meta['title']}",
                    extra={"markup": True},
                )
                return

            # 3. 下载封面
            has_cover = False
            if meta.get("coverId"):
                try:
                    cover_uuid = meta["coverId"].replace("-", "/")
                    cover_url = (
                        f"https://resources.tidal.com/images/{cover_uuid}/1280x1280.jpg"
                    )

                    resp = fetch_get(cover_url)
                    if resp.content and len(resp.content) > 0:
                        with open(temp_cover, "wb") as f:
                            f.write(resp.content)
                        has_cover = True
                        logger.info(
                            f"   -> 🖼️  封面下载成功 ({len(resp.content) // 1024} KB)"
                        )
                    else:
                        logger.warning("   -> ⚠️  封面文件为空")
                except Exception as e:
                    logger.warning(f"   -> ⚠️  封面下载失败: {e}")

            # 4. 下载歌词
            lyrics = self.api.get_lyrics(track_id)
            if lyrics:
                lyric_text = str(lyrics.get("text", ""))
                with open(temp_lyrics, "w", encoding="utf-8") as f:
                    f.write(lyric_text)
                if lyrics.get("isLrc") and config["lyrics"]["save_lrc"]:
                    lrc_path = folder_path / f"{filename}.lrc"
                    with open(lrc_path, "w", encoding="utf-8") as f:
                        f.write(lyric_text)

            # 5. 混流
            logger.info(f"💿 [cyan][6/6][/cyan] 混流封装...", extra={"markup": True})
            embed_metadata(
                temp_audio,
                temp_cover if has_cover else None,
                temp_lyrics if lyrics else None,
                meta,
                final_path,
            )
            logger.info(
                f"✅ [bold green]完成:[/bold green] {final_path.name}\n",
                extra={"markup": True},
            )

        except Exception as e:
            logger.error(f"❌ 处理歌曲出错: {e}")
        finally:
            for p in [temp_audio, temp_cover, temp_lyrics]:
                if p.exists():
                    try:
                        p.unlink()
                    except:
                        pass

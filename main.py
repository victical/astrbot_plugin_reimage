from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, llm_tool
import os
import json
import base64
import httpx
import re
import asyncio
from datetime import datetime, timedelta
import astrbot.api.message_components as Comp
from urllib.parse import urlparse

@register("astrbot_plugin_reimage", "Victical", "图像识别插件", "0.0.1", "https://github.com/victical/astrbot_plugin_reimage")
class ImageRecognitionPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # 从配置中加载设置
        self.config = config.get("img_provider", {})
        self.provider_id = self.config.get("provider_id", "img_provider")
        self.system_prompt = self.config.get("system_prompt", "描述图片中的内容，控制在50字以内。")

    def is_valid_url(self, url: str) -> bool:
        """检查URL是否有效"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    async def download_image(self, url: str) -> str:
        """下载图片并返回本地路径"""
        try:
            # 创建临时目录
            temp_dir = os.path.join(os.path.dirname(__file__), "temp")
            os.makedirs(temp_dir, exist_ok=True)

            # 生成临时文件名
            file_name = os.path.basename(urlparse(url).path)
            if not file_name:
                file_name = f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            local_path = os.path.join(temp_dir, file_name)

            # 下载图片
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(response.content)

            return local_path
        except Exception as e:
            logger.error(f"下载图片失败: {str(e)}")
            raise

    async def call_openai_api(self, event: AstrMessageEvent, prompt: str, image_url: str) -> str:
        """调用API进行图像分析"""
        # 获取图像识别provider
        img_provider = self.context.get_provider_by_id(self.provider_id)
        if not img_provider:
            raise Exception(f"未找到图像识别provider，请在配置中设置id为'{self.provider_id}'的图像模型")

        # 处理图片URL：本地文件路径转为 base64 数据
        if image_url.startswith("file://"):
            image_url = image_url[7:]
        if not self.is_valid_url(image_url):
            if os.path.exists(image_url):
                with open(image_url, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(image_url)[1].lstrip(".").lower() or "png"
                if ext == "jpg":
                    ext = "jpeg"
                image_url = f"data:image/{ext};base64,{img_b64}"
                logger.info(f"图片为本地文件，已转为 base64 编码: {image_url[:64]}...")
            else:
                raise Exception(f"无效的图片URL: {image_url}")

        try:
            # 构建图像识别请求
            img_req = event.request_llm(
                prompt=prompt,
                image_urls=[image_url],
                system_prompt=self.system_prompt
            )

            # 调用图像识别provider
            img_response = await img_provider.text_chat(**img_req.__dict__)
            if img_response.role != "assistant":
                raise Exception("图像分析失败")
            
            # 直接返回图像分析结果
            return img_response.completion_text

        except Exception as e:
            logger.error(f"处理图片时出错: {str(e)}")
            raise

    def get_image_from_message(self, message) -> str:
        """从消息链中获取图片URL"""
        try:
            # 打印原始消息和消息链内容
            logger.debug(f"原始消息: {message}")
            logger.debug(f"消息链内容: {message}")

            # 遍历消息链
            for component in message:
                # 打印每个组件的类型和内容
                logger.debug(f"组件类型: {type(component).__name__}")
                logger.debug(f"组件内容: {component.__dict__}")

                # 检查是否是图片组件
                if isinstance(component, Comp.Image):
                    # 使用url属性
                    if hasattr(component, 'url') and component.url:
                        logger.info(f"找到图片URL: {component.url}")
                        return component.url
                    else:
                        logger.debug(f"图片组件属性: {dir(component)}")
            return None
        except Exception as e:
            logger.error(f"获取图片失败: {str(e)}")
            return None

    @llm_tool(name="image-analysis")
    async def analyze_image(self, event: AstrMessageEvent, message: str = "") -> str:
        """
        分析图片内容。当用户发送包含图片的消息时，调用此函数。
        函数会自动识别消息中的图片，并生成图片描述。

        Args:
            message (string): 用户的消息内容

        Returns:
            string: 生成的图片描述或错误信息
        """
        # 从消息链中获取图片
        image_url = self.get_image_from_message(event.message_obj.message)
        if not image_url:
            return "未检测到图片，请发送包含图片的消息"
        
        try:
            # 使用API进行图像分析
            analysis_result = await self.call_openai_api(event, "请分析这张图片的内容", image_url)
            return analysis_result
        except Exception as e:
            logger.error(f"处理图片时出错: {str(e)}")
            return f"处理过程中出现错误：{str(e)}"

    async def terminate(self):
        """插件卸载时的清理工作"""
        # 清理临时目录
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        if os.path.exists(temp_dir):
            try:
                for file in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, file))
                os.rmdir(temp_dir)
            except:
                pass

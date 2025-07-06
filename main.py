from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, llm_tool
import os
import json
import httpx
import re
import asyncio
from datetime import datetime, timedelta
import astrbot.api.message_components as Comp
from urllib.parse import urlparse
import base64

@register("astrbot_plugin_reimage", "Victical", "图像识别插件", "0.0.1", "https://github.com/victical/astrbot_plugin_reimage")
class ImageRecognitionPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config.get("img_provider", {})
        self.provider_id = self.config.get("provider_id", "img_provider")
        self.system_prompt = self.config.get("system_prompt", "描述图片中的内容，控制在50字以内。")

    def is_valid_url(self, url: str) -> bool:
        if os.path.exists(url):
            return True
        try:
            result = urlparse(url)
            return all([result.scheme in ['http', 'https'], result.netloc])
        except:
            return False

    async def download_image(self, url: str) -> str:
        try:
            temp_dir = os.path.join(os.path.dirname(__file__), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            file_extension = os.path.splitext(urlparse(url).path)[1] or ".png"
            file_name = f"image_{timestamp}{file_extension}"
            local_path = os.path.join(temp_dir, file_name)
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(response.content)
            return local_path
        except Exception as e:
            logger.error(f"下载图片失败: {str(e)}")
            raise
            
    def get_image_from_message(self, message) -> str:
        try:
            for component in message:
                if isinstance(component, Comp.Image):
                    if hasattr(component, 'url') and component.url:
                        logger.info(f"找到图片URL: {component.url}")
                        return component.url
            return None
        except Exception as e:
            logger.error(f"获取图片失败: {str(e)}")
            return None

    def encode_image_to_base64(self, file_path: str) -> str:
        with open(file_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/jpeg;base64,{encoded_string}"

    async def call_api_directly(self, prompt: str, image_data_url: str) -> str:
        logger.info("Bypassing framework. Calling API directly...")
        provider = self.context.get_provider_by_id(self.provider_id)
        if not provider:
            raise Exception(f"未找到指定的 Provider: '{self.provider_id}'。请检查插件配置是否正确填写了 Provider ID。")

        config = provider.provider_config
        api_base = config.get("api_base")
        api_key = provider.get_current_key()
        model_name = config.get("model_config", {}).get("model")

        if not all([api_base, api_key, model_name]):
            raise Exception("Provider 配置不完整 (缺少 api_base, key, 或 model)")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url}
                        }
                    ]
                }
            ],
            "max_tokens": 1024
        }

        async with httpx.AsyncClient(timeout=120) as client:
            logger.info(f"Sending direct request to {api_base} for model {model_name}")
            response = await client.post(f"{api_base}/chat/completions", json=payload, headers=headers)
            response.raise_for_status() 
            result_json = response.json()
            logger.debug(f"Direct API response: {result_json}")
            
            if result_json.get("choices") and len(result_json["choices"]) > 0:
                content = result_json["choices"][0].get("message", {}).get("content")
                if content:
                    return content.strip()
        raise Exception("从直接 API 调用中未能解析出有效内容")

    @llm_tool(name="image-analysis")
    async def analyze_image(self, event: AstrMessageEvent, message: str = "") -> str:
        image_url = self.get_image_from_message(event.message_obj.message)
        if not image_url:
            return "未检测到图片，请发送包含图片的消息"
        
        local_image_path = None
        try:
            local_image_path = await self.download_image(image_url)
            image_data_url = self.encode_image_to_base64(local_image_path)
            analysis_result = await self.call_api_directly("请分析这张图片的内容", image_data_url)
            return analysis_result
        except Exception as e:
            logger.error(f"处理图片时出错 (直接调用模式): {str(e)}")
            return f"处理过程中出现错误：{str(e)}"
        finally:
            if local_image_path and os.path.exists(local_image_path):
                try:
                    os.remove(local_image_path)
                except Exception as e:
                    logger.error(f"删除临时文件失败: {str(e)}")

    async def terminate(self):
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        if os.path.exists(temp_dir):
            try:
                for file_name in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file_name)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                os.rmdir(temp_dir)
            except Exception as e:
                logger.error(f"清理temp目录时出错: {e}")
# astrbot_plugin_reimage - 图像内容转述

## 🤝 介绍
智能图像识别、内容分析

## 📦 安装
直接在astrbot的插件市场搜索astrbot_plugin_reimage，点击安装，等待完成即可

也可以克隆源码到插件文件夹：

```bash
# 克隆仓库到插件目录
cd /AstrBot/data/plugins
git clone https://github.com/victical/astrbot_plugin_reimage
```

## ⌨️ 配置
请前往插件配置面板进行配置：

- `provider_id`: 图像识别模型ID（默认为 "img_provider"）
- `system_prompt`: 系统提示词（默认为 "描述图片中的内容，控制在50字以内。"）

## 🛠️ 使用说明

插件会自动识别消息中的图片，无需使用特定命令。会自动进行分析并返回描述。


## 📝 许可证
MIT License

## 提示
 AstrBotv3.5.18存在一个 Bug:框架会忽略插件指定的 rovider而使用默认 Provider。导致这个插件失效，这个版本直接向provider的api发送请求绕过这个bug。
 相关 Bug :https://github.com/AstrBotDevs/AstrBot/issues/2048
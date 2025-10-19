# 纳西妲对话应用

这是一个融合了Live2D模型和对话功能的应用，将原本静态的纳西妲图片（其实最开始是terminal）替换为动态的Live2D模型，保留了表情、动作和嘴型随声音大小变换的功能。

## 功能特点

- 动态Live2D模型展示（纳西妲）
- 对话交互功能（使用DeepSeek API）
- 语音合成（GPT-SoViTS）
- 嘴型随声音大小实时变换
- 表情与动作随对话内容的推进而改变
- 背景音乐播放

## 安装依赖

在运行应用前，请确保安装了以下依赖：

```bash
pip install flask requests librosa numpy openai
```

## 运行步骤

1. 确保GSV目录下的TTS服务已经启动（利用该项目的api.py启动，端口为9880）

2. 运行应用：

```bash
python app.py
```

3. 打开浏览器，访问 http://localhost:5000

## 注意事项

- 如果Live2D模型加载失败，会尝试加载备用模型
- 确保网络连接正常，以便加载必要的JavaScript库
- 请确保在app.py中填入正确的Deepseek API key
- 请确定GSV/appi.bat中的python运行环境是GSV自带的runtime还是你的系统中的默认python环境

## 文件说明

- `app.py`: 主应用文件
- `templates/index.html`: 前端页面
- `static/style.css`: 页面样式
- `static/js/script.js`: 前端交互和Live2D控制逻辑
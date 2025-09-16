# 纳西妲对话应用

这是一个融合了Live2D模型和对话功能的应用，将原本静态的纳西妲图片替换为动态的Live2D模型，保留了表情、动作和嘴型随声音大小变换的功能。

## 功能特点

- 动态Live2D模型展示（纳西妲）
- 对话交互功能（使用DeepSeek API）
- 语音合成（使用原有的TTS模块）
- 嘴型随声音大小实时变换
- 背景音乐播放

## 安装依赖

在运行应用前，请确保安装了以下依赖：

```bash
pip install flask requests librosa pygame numpy
```

## 运行步骤

1. 确保GSV目录下的TTS服务已经启动（端口9880）

2. 运行应用：

```bash
python app.py
```

3. 打开浏览器，访问 http://localhost:5000

## 注意事项

- 应用运行时会在live2d目录下创建tmp.txt文件用于存储嘴型数据
- 应用使用多线程处理TTS和音频播放，以避免阻塞主线程
- 如果Live2D模型加载失败，会尝试加载备用模型
- 确保网络连接正常，以便加载必要的JavaScript库

## 文件说明

- `app.py`: 主应用文件
- `templates/index.html`: 前端页面
- `static/js/script.js`: 前端交互和Live2D控制逻辑
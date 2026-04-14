"""
TTS WebSocket Server for GPT-SoVITS v2ProPlus
"""

import os
import sys
import traceback
import asyncio
import websockets
import json
import numpy as np
import torch

now_dir = os.getcwd()
sys.path.append(now_dir)
sys.path.append("%s/GPT_SoVITS" % (now_dir))

from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
from tools.i18n.i18n import I18nAuto

i18n = I18nAuto()

# 配置参数
config_path = "GPT_SoVITS/configs/tts_infer.yaml"
ref_audio_path = "models/不知道干什么的话，要不要我带你去转转呀？.wav"
prompt_text = "不知道干什么的话，要不要我带你去转转呀？"
prompt_lang = "zh"
text_lang = "zh"

# 初始化TTS配置
tts_config = TTS_Config(config_path)
# 强制使用v2ProPlus配置
tts_config.update_version("v2ProPlus")
# 设置模型路径
tts_config.t2s_weights_path = "models/nahida-e15.ckpt"
tts_config.vits_weights_path = "models/nahida_e8_s1256.pth"
# 设置设备和精度
tts_config.device = "cuda" if torch.cuda.is_available() else "cpu"
tts_config.is_half = False  # 根据需要调整

print("TTS Config:", tts_config)

# 初始化TTS管道
tts_pipeline = TTS(tts_config)

# 设置参考音频
tts_pipeline.set_ref_audio(ref_audio_path)

async def tts_handler(websocket):
    try:
        async for message in websocket:
            # 解析客户端发送的JSON消息
            try:
                data = json.loads(message)
                text = data.get("text", "")
                # 使用客户端发送的参数，如果未提供则使用默认值
                tts_params = {
                    "text": text,
                    "text_lang": data.get("text_lang", text_lang),
                    "ref_audio_path": data.get("ref_audio_path", ref_audio_path),
                    "prompt_text": data.get("prompt_text", prompt_text),
                    "prompt_lang": data.get("prompt_lang", prompt_lang),
                    "top_k": data.get("top_k", 5),
                    "top_p": data.get("top_p", 0.95),
                    "temperature": data.get("temperature", 0.9),
                    "text_split_method": data.get("text_split_method", "cut5"),
                    "batch_size": data.get("batch_size", 1),
                    "batch_threshold": data.get("batch_threshold", 0.75),
                    "speed_factor": data.get("speed_factor", 1.0),
                    "repetition_penalty": data.get("repetition_penalty", 1.35),
                    "fragment_interval": data.get("fragment_interval", 0.3),
                    "split_bucket": data.get("split_bucket", True),
                    "return_fragment": data.get("return_fragment", False),
                    "seed": data.get("seed", -1),
                    "parallel_infer": data.get("parallel_infer", True), 
                }
            except json.JSONDecodeError:
                # 如果不是JSON格式，保持原来的处理方式
                text = message
                tts_params = {
                    "text": text,
                    "text_lang": text_lang,
                    "ref_audio_path": ref_audio_path,
                    "prompt_text": prompt_text,
                    "prompt_lang": prompt_lang,
                    "top_k": 5,
                    "top_p": 0.95,
                    "temperature": 0.9,
                    "text_split_method": "cut5",
                    "batch_size": 1,
                    "batch_threshold": 0.75,
                    "speed_factor": 1.0,
                    "repetition_penalty": 1.35,
                    "fragment_interval": 0.3,
                    "split_bucket": True,
                    "return_fragment": False,
                    "seed": -1,
                    "parallel_infer": True, 
                }
            
            if not text:
                await websocket.send(json.dumps({"error": "Text is required"}))
                continue
            
            print(f"Received text: {text}")
            
            # 执行TTS推理
            audio_generator = tts_pipeline.run(tts_params)
            
            # 检查是否启用流式传输
            return_fragment = tts_params.get("return_fragment", False)
            
            if return_fragment:
                # 流式传输：逐个发送音频片段
                print("Streaming audio fragments...")
                for i, (sampling_rate, audio_data) in enumerate(audio_generator):
                    # 确保音频数据是正确的格式
                    if audio_data.dtype != np.int16:
                        # 转换为16位整数格式
                        audio_data = (audio_data * 32767).astype(np.int16)
                    
                    # 将音频数据转换为字节流
                    audio_bytes = audio_data.tobytes()
                    
                    # 发送音频数据片段
                    await websocket.send(audio_bytes)
                    print(f"Sent fragment {i+1}: {len(audio_bytes)} bytes")
                
                # 发送结束信号
                end_signal = json.dumps({"status": "END_OF_TRANSMISSION"})
                await websocket.send(end_signal)
                print("Sent end of transmission signal")
            else:
                # 非流式传输：获取完整音频数据并一次性发送
                print("Sending complete audio...")
                # 获取音频数据
                sampling_rate, audio_data = next(audio_generator)
                
                # 确保音频数据是正确的格式
                if audio_data.dtype != np.int16:
                    # 转换为16位整数格式
                    audio_data = (audio_data * 32767).astype(np.int16)
                
                # 将音频数据转换为字节流
                audio_bytes = audio_data.tobytes()
                
                # 发送音频数据
                await websocket.send(audio_bytes)
                print(f"Sent complete audio: {len(audio_bytes)} bytes")
            
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        await websocket.send(json.dumps({"error": str(e)}))

# 启动WebSocket服务器
async def main():
    # 增加max_size参数以允许更大的消息（10MB）
    server = await websockets.serve(tts_handler, "127.0.0.1", 9880, max_size=10*1024*1024)
    print("WebSocket TTS Server started on ws://127.0.0.1:9880")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())

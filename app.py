import os, requests
import librosa
import time
import numpy as np
import os
import requests
from flask import Flask, render_template, request, jsonify, Response, send_from_directory

app = Flask(__name__)
history = [{"role": "system", "content": "你将扮演《原神》中的纳西妲。在输出时，你必须在每一句带有情感色彩的句子前添加情感或动作标签，例如：“[祈祷]愿繁花与叶铺就你冒险的前路。”如果没有情感色彩，你可以省略标签。标签一共有祈祷、发光、翻花绳、好奇、泪、脸黑、脸红、生气、星星等九种，一定不要输出没有列出的标签！"}]

now_dir = os.getcwd()
all_files = os.listdir(now_dir + r'\GSV\models') 
ckpt_files = [filename for filename in all_files if filename.endswith('.ckpt')]
pth_files = [filename for filename in all_files if filename.endswith('.pth')]
ref_audio_list = [filename for filename in all_files if filename.endswith('.wav')]
ckptfile=ckpt_files[0]
pthfile=pth_files[0]
ref_audio=ref_audio_list[0]

# Live2D相关配置
live2d_dir = os.path.join(now_dir, 'live2d')
tmp_txt_path = os.path.join(live2d_dir, 'tmp.txt')

def returnData(textt):
    data = {
            "text": textt,
            "text_lang": "auto",
            
            "ref_audio_path": now_dir + f"/GSV/models/{ref_audio}",         
            "prompt_text": ref_audio.split('.wav')[0],
            "prompt_lang": "zh",
            
            "top_k": 7,
            "top_p": 1,
            "temperature": 1,
            "speed_factor": 1,
            "media_type": 'wav',
            
            "split_bucket": True,
            "parallel_infer": True,
            "repetition_penalty": 1.35
        }
    return data

def split_say(sc):
    if '（' in sc:
        z = '（'
        y = '）'
    else:
        z = '('
        y = ')'
    sc = sc.split(z)
    ans = []
    for i in sc:
        if y in i:
            ans.append(i.split(y)[1])
        else:
            ans.append(i)
    return ''.join(ans)

# 获取TTS音频数据
def get_tts_audio_data(text):
    try:
        # 调用TTS服务获取音频
        text = split_say(text)
        tts_response = requests.get(f"http://127.0.0.1:9880/tts", params=returnData(text))
        if tts_response.status_code == 200:
            return tts_response.content
        else:
            print(f"TTS服务异常，状态码: {tts_response.status_code}")
            return None
    except Exception as e:
        print(f"获取TTS音频失败: {e}")
        return None

# 直接处理音频数据并生成嘴型数据
def process_audio_for_mouth_shape(audio_data):
    try:
        # 直接从二进制数据加载音频
        import io
        audio_buffer = io.BytesIO(audio_data)
        x, sr = librosa.load(audio_buffer, sr=8000)
        
        # 音频处理
        x = x - min(x)
        max_val = max(x) if max(x) > 0 else 1  # 避免除零错误
        x = x / max_val
        x = np.log(x + 1e-10) + 1  # 添加小值避免log(0)
        max_val = max(x) if max(x) > 0 else 1
        x = x / max_val * 1.2
        
        # 生成嘴型数据点，每秒30个点（33ms间隔）
        duration = len(x) / sr
        sample_interval = sr / 30  # 每秒30个样本
        mouth_shape_data = []
        
        for i in range(0, len(x), int(sample_interval)):
            # 取区间内的最大值作为该时间点的值
            end_idx = min(i + int(sample_interval), len(x))
            val = max(x[i:end_idx]) if i < end_idx else 0
            val = max(0, val)  # 确保值为非负
            mouth_shape_data.append(float(val))
        
        return {
            "duration": float(duration),
            "mouth_shape_data": mouth_shape_data
        }
    except Exception as e:
        print(f"音频处理失败: {e}")
        return None

# 直接处理音频数据并更新嘴型数据
def play_audio_and_update_mouth(audio_data):
    try:
        # 直接从二进制数据加载音频
        import io
        audio_buffer = io.BytesIO(audio_data)
        x, sr = librosa.load(audio_buffer, sr=8000)
        
        # 音频处理
        x = x - min(x)
        max_val = max(x) if max(x) > 0 else 1  # 避免除零错误
        x = x / max_val
        x = np.log(x + 1e-10) + 1  # 添加小值避免log(0)
        max_val = max(x) if max(x) > 0 else 1
        x = x / max_val * 1.2
        
        # 更新文本文件（为了兼容现有Live2D前端）
        s_time = time.time()
        
        try:
            for _ in range(int(len(x) / 800)):
                current_idx = int((time.time() - s_time) * 8000) + 1
                if 0 <= current_idx < len(x):
                    it = x[current_idx]
                    it = max(0, it)  # 确保值为非负
                    with open(tmp_txt_path, "w") as f:
                        f.write(str(float(it)))
                time.sleep(0.1)
        except Exception as e:
            print(f"音频处理循环出错: {e}")
            pass
            
    except Exception as e:
        print(f"音频加载或处理失败: {e}")
        
    # 确保最终状态为0
    with open(tmp_txt_path, "w") as f:
        f.write("0")

# Live2D相关路由
@app.route('/live2d_assets/<path:path>')
def serve_live2d_assets(path):
    assets_path = os.path.join(live2d_dir, 'dist', 'assets')
    return send_from_directory(assets_path, path)

# 获取嘴型数据点的API接口（用于前端同步）
@app.route('/api/get_mouth_shape_data')
def get_mouth_shape_data():
    try:
        # 从请求参数中获取文本
        text = request.args.get('text', '')
        if not text:
            return jsonify({"error": "文本不能为空"}), 400
            
        # 获取TTS音频数据（不保存临时文件）
        audio_data = get_tts_audio_data(text)
        if not audio_data:
            return jsonify({"error": "获取音频失败"}), 500
            
        # 处理音频生成嘴型数据
        result = process_audio_for_mouth_shape(audio_data)
        if result:
            return jsonify(result)
        else:
            return jsonify({"error": "处理音频失败"}), 500
    except Exception as e:
        print(f"获取嘴型数据失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get_mouth_y')
def get_mouth_y():
    try:
        if os.path.exists(tmp_txt_path):
            with open(tmp_txt_path, "r") as f:
                content = f.read().strip()
                return jsonify({"y": content})
        else:
            return jsonify({"y": "0"})
    except Exception as e:
        print(f"读取嘴型数据失败: {e}")
        return jsonify({"y": "0"})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/ask', methods=['POST'])
def ask():
    user_input = request.json.get("message")
    api_key="sk-c613f87202844699ba44e1c4d06e255e"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    history.append({"role": "user", "content": user_input})
    data = {
        "model": "deepseek-chat",
        "messages": history
    }
    response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data)
    result = response.json()

    reply = result.get("choices", [{}])[0].get("message", {}).get("content", "出错了，请稍后再试。")
    print(f"回复: {reply}")
    history.append({"role": "assistant", "content": reply})
    
    # 异步处理TTS和嘴型同步
    import threading
    def process_tts():
        audio_data = get_tts_audio_data(reply)
        if audio_data:
            play_audio_and_update_mouth(audio_data)
    
    threading.Thread(target=process_tts).start()
    
    return jsonify({"reply": reply})

@app.route("/api/tts", methods=["POST"])
def tts():
    text = split_say(request.json.get("text"))

    try:
        tts_response = requests.get(f"http://127.0.0.1:9880/tts",params=returnData(text))
        if tts_response.status_code != 200:
            raise Exception("TTS 服务异常")

        return Response(tts_response.content, mimetype="audio/wav")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # 确保tmp.txt文件存在
    if not os.path.exists(tmp_txt_path):
        with open(tmp_txt_path, "w") as f:
            f.write("0")
    app.run(host='0.0.0.0', port=5000, debug=True)
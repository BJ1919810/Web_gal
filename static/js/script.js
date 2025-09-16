// Web_Gal 角色互动系统

// 集中管理应用的核心状态和资源
const AppState = {
    // 音频相关状态
    isVoicePlaying: false,
    audioContext: null,
    analyser: null,
    audioSource: null,
    activeAudioUrl: null,
    
    // 模型相关状态
    model: null,
    app: null,
    
    // 动画状态
    animationFrameId: null
};

/**
 * DOM元素缓存
 * 避免重复查询DOM
 */
const DOM = {
    voicePlayer: null,
    bgm: null,
    canvas: null,
    dialogue: null,
    userInput: null,
    submitBtn: null
};

/**
 * 初始化应用
 * 入口函数，负责启动整个应用
 */
async function initApp() {
    try {
        // 缓存DOM元素
        cacheDOM();
        
        // 初始化音频上下文
        initAudioContext();
        
        // 初始化Live2D模型
        await initLive2D();
        
        // 初始化对话系统
        initDialogueSystem();
        
        // 初始化背景音乐
        initBGM();
        
        console.log('WebGAL应用初始化完成');
    } catch (error) {
        console.error('应用初始化失败:', error);
    }
}

/**
 * 缓存DOM元素
 */
function cacheDOM() {
    DOM.voicePlayer = document.getElementById('voice-player');
    DOM.bgm = document.getElementById('bgm');
    DOM.canvas = document.getElementById('canvas2');
    DOM.dialogue = document.getElementById('dialogue');
    DOM.userInput = document.getElementById('user-input');
    DOM.submitBtn = document.getElementById('submit-btn');
}

/**
 * 初始化音频上下文
 */
function initAudioContext() {
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        AppState.audioContext = new AudioContext();
        
        // 创建分析器，设置合适的参数以平衡性能和精度
        AppState.analyser = AppState.audioContext.createAnalyser();
        AppState.analyser.fftSize = 256; // 较小的fftSize以提高性能
        AppState.analyser.smoothingTimeConstant = 0.3; // 平滑系数，使变化更自然
        
    } catch (error) {
        console.warn('初始化音频上下文失败，将使用模拟口型:', error);
    }
}

/**
 * 初始化Live2D模型
 */
async function initLive2D() {
    try {
        // 动态加载pixi-live2d-display库
        await loadLive2DLibrary();
        
        // 获取Live2DModel类
        const Live2DModel = getLive2DModelClass();
        if (!Live2DModel) {
            throw new Error('无法找到Live2DModel类');
        }
        
        // 创建PIXI应用
        AppState.app = new PIXI.Application({
            view: DOM.canvas,
            autoStart: true,
            resizeTo: window,
            transparent: true
        });
        
        // 加载模型
        AppState.model = await loadLive2DModel(Live2DModel);
        if (!AppState.model) {
            throw new Error('所有Live2D模型加载失败');
        }
        
        // 设置模型
        setupModel();
        
        // 监听窗口大小变化
        window.addEventListener('resize', updateModelTransform);
        
    } catch (error) {
        console.error('Live2D初始化失败:', error);
        showModelError();
    }
}

/**
 * 动态加载Live2D库
 */
function loadLive2DLibrary() {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/index.min.js';
        script.onload = resolve;
        script.onerror = () => reject(new Error('Live2D库加载失败'));
        document.body.appendChild(script);
    });
}

/**
 * 获取Live2DModel类
 * 处理不同的库导出方式
 */
function getLive2DModelClass() {
    return window.Live2DModel || 
           (window.pixi_live2d_display && window.pixi_live2d_display.Live2DModel) ||
           (PIXI.live2d && PIXI.live2d.Live2DModel);
}

/**
 * 加载Live2D模型
 */
async function loadLive2DModel(Live2DModel) {
    const modelPaths = [
        '/live2d_assets/nahida/草神.model3.json',
        '/live2d_assets/shizuku/shizuku.model.json'
    ];
    
    for (const modelPath of modelPaths) {
        try {
            console.log('尝试加载Live2D模型:', modelPath);
            
            // 检查模型文件是否存在
            const response = await fetch(modelPath);
            if (!response.ok) continue;
            
            // 加载模型
            const model = await Live2DModel.from(modelPath, {autoInteract: false});
            console.log('Live2D模型加载成功:', modelPath);
            return model;
            
        } catch (error) {
            console.warn('Live2D模型加载失败:', error);
        }
    }
    
    return null;
}

/*
 * 设置模型
 *  - 按下鼠标时开始跟随（平滑）
 *  - 松开/离开画布时停止跟随并回正
 *  - 带灵敏度和缓动，让视线更自然
 */
function setupModel() {
    // 添加模型到舞台
    AppState.app.stage.addChild(AppState.model);

    // 初始化模型变换
    updateModelTransform();

    const canvas = DOM.canvas;
    if (!canvas || !AppState.model) return;

    // 当前角度 / 目标角度
    let currentX = 0, currentY = 0;
    let targetX = 0, targetY = 0;
    let pointerMoveHandler = null;

    // 鼠标按下：开始跟随
    const handlePointerDown = (e) => {
        updateTarget(e.clientX, e.clientY); // 立刻设置目标
        pointerMoveHandler = (ev) => updateTarget(ev.clientX, ev.clientY);
        window.addEventListener('pointermove', pointerMoveHandler);
    };

    // 松开或离开：停止并回正
    const stopFollow = () => {
        if (pointerMoveHandler) {
            window.removeEventListener('pointermove', pointerMoveHandler);
            pointerMoveHandler = null;
        }
        // 让目标缓慢回正
        targetX = 0;
        targetY = 0;
    };

    // 工具函数：更新目标角度
    function updateTarget(clientX, clientY) {
        const rect = canvas.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;

        // 相对偏移，范围 [-1, 1]
        const dx = (clientX - centerX) / (rect.width / 2);
        const dy = (clientY - centerY) / (rect.height / 2);

        // 灵敏度（越小越温和）
        const sensitivity = 0.4;
        const nx = Math.max(-1, Math.min(1, dx * sensitivity));
        const ny = Math.max(-1, Math.min(1, dy * sensitivity));

        // 最大角度
        targetX = -nx * 50; // 左右最大 50°
        targetY = -ny * 50; // 上下最大 50°
    }

    // 每帧缓动更新视线
    AppState.app.ticker.add(() => {
        // 线性插值（0.15 越大响应越快）
        currentX += (targetX - currentX) * 0.15;
        currentY += (targetY - currentY) * 0.15;

        const core = AppState.model.internalModel.coreModel;
        core.setParameterValueById('ParamAngleX', currentX);
        core.setParameterValueById('ParamAngleY', currentY);
        core.setParameterValueById('ParamEyeBallX', currentX / 30); // 眼球范围较小
        core.setParameterValueById('ParamEyeBallY', currentY / 30);
        core.saveParameters();
    });

    // 绑定事件
    canvas.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointerup', stopFollow);
    canvas.addEventListener('mouseleave', stopFollow);
}

/**
 * 更新模型变换
 */
function updateModelTransform() {
    if (!AppState.model || !AppState.app) return;
    
    const app = AppState.app;
    const model = AppState.model;
    
    // 根据屏幕高度调整缩放比例
    const scale = app.screen.height * 0.0002;
    model.scale.set(scale);
    
    // 设置模型居中位置
    model.anchor.set(0.5, 0.5);
    model.x = app.screen.width / 2;  // 水平居中
    model.y = app.screen.height * 0.7; // 向上调整垂直位置
    
    // 设置旋转和倾斜
    model.rotation = Math.PI;
    model.skew.x = Math.PI;
}

/**
 * 显示模型加载错误
 */
function showModelError() {
    const ctx = DOM.canvas.getContext('2d');
    if (!ctx) return;
    
    ctx.fillStyle = 'white';
    ctx.font = '16px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('Live2D模型加载失败', DOM.canvas.width / 2, DOM.canvas.height / 2);
}

/**
 * 初始化对话系统
 */
function initDialogueSystem() {
    if (!DOM.userInput || !DOM.submitBtn || !DOM.dialogue) {
        console.error('对话系统DOM元素缺失');
        return;
    }
    
    // 绑定点击按钮事件
    DOM.submitBtn.addEventListener('click', handleUserInput);
    
    // 绑定Enter键事件
    DOM.userInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            handleUserInput();
        }
    });
}

/**
 * 处理用户输入
 */
async function handleUserInput() {
    const inputText = DOM.userInput.value.trim();
    if (!inputText) return;
    
    // 清空输入框并显示思考状态
    DOM.userInput.value = '';
    DOM.dialogue.textContent = '思考中……';
    
    try {
        // 获取回复
        const reply = await getAIReply(inputText);
        
        // 播放语音
        await playVoice(reply);
        
        // 使用打字机效果显示对话
        typewriterEffect(DOM.dialogue, reply);
        
    } catch (error) {
        console.error('处理对话失败:', error);
        DOM.dialogue.textContent = '出错了，请稍后再试。';
    }
}

/**
 * 打字机效果函数
 * 使文本一个字一个字地显示出来
 * param {HTMLElement} element - 要显示文本的DOM元素
 * param {string} text - 要显示的文本内容
 * param {number} speed - 每个字之间的延迟时间（毫秒）
 * param {Function} callback - 文本显示完成后的回调函数
 */
function typewriterEffect(element, text, speed = 50, callback = null) {
    if (!element) return;
    
    let index = 0;
    element.textContent = '';
    
    function typeNext() {
        if (index < text.length) {
            // 添加下一个字符
            element.textContent += text.charAt(index);
            index++;
            
            // 设置下一个字符的定时器
            setTimeout(typeNext, speed);
        } else if (callback) {
            // 文本显示完成，执行回调
            callback();
        }
    }
    
    // 开始打字效果
    typeNext();
}

/**
 * 获取AI回复
 */
async function getAIReply(message) {
    try {
        const response = await fetch('/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        
        if (!response.ok) {
            throw new Error(`API请求失败: ${response.status}`);
        }
        
        const data = await response.json();
        return data.reply;
        
    } catch (error) {
        console.error('获取AI回复失败:', error);
        throw error;
    }
}

/**
 * 初始化背景音乐
 */
function initBGM() {
    if (!DOM.bgm) {
        console.warn('背景音乐元素缺失');
        return;
    }
    
    // 监听用户交互以触发音频播放（浏览器策略要求）
    window.addEventListener('click', () => {
        if (DOM.bgm.paused) {
            DOM.bgm.play().catch(e => {
                console.warn('背景音乐播放失败:', e);
            });
        }
    }, { once: true });
}

/**
 * 播放语音
 */
async function playVoice(text) {
    // 重置之前的状态
    resetVoiceState();
    
    if (!DOM.voicePlayer) {
        console.error('语音播放器元素不存在');
        fallbackMouthAnimation(); // 即使没有播放器也显示口型动画
        return;
    }
    
    try {
        // 请求TTS服务获取语音
        const blob = await fetchTTSAudio(text);
        
        // 检查获取的blob是否有效
        if (!blob || blob.size === 0) {
            throw new Error('获取到的音频数据为空');
        }
        
        // 创建音频URL
        AppState.activeAudioUrl = URL.createObjectURL(blob);
        
        // 完全重置音频元素，这是解决"already connected"错误的关键
        resetAudioElement(DOM.voicePlayer);
        
        // 设置音频源
        DOM.voicePlayer.src = AppState.activeAudioUrl;
        
        // 预加载音频
        await DOM.voicePlayer.load();
        
        // 连接音频分析器 - 使用全新的策略
        if (!connectAudioAnalyser()) {
            // 如果连接分析器失败，使用备用口型动画
            console.warn('音频分析器连接失败，将使用模拟口型动画');
        }
        
        // 开始播放语音
        await DOM.voicePlayer.play();
        AppState.isVoicePlaying = true;
        
        // 开始口型同步或使用备用动画
        if (AppState.analyser) {
            startMouthShapeSync();
        } else {
            fallbackMouthAnimation();
        }
        
        // 播放结束后清理
        DOM.voicePlayer.onended = function() {
            // 确保在清理前等待一小段时间
            setTimeout(cleanupVoicePlayback, 100);
        };
        
    } catch (error) {
        console.error('播放语音失败:', error);
        // 确保即使在错误情况下也正确清理资源
        setTimeout(() => {
            resetVoiceState();
            // 播放失败时使用模拟口型动画
            fallbackMouthAnimation();
        }, 100);
    }
}

/**
 * 请求TTS音频
 */
async function fetchTTSAudio(text) {
    try {
        const response = await fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        
        if (!response.ok) {
            throw new Error(`TTS请求失败: ${response.status}`);
        }
        
        return await response.blob();
        
    } catch (error) {
        console.error('获取TTS音频失败:', error);
        throw error;
    }
}

/**
 * 完全重置音频元素
 * 这是解决"already connected"错误的关键策略
 * param {HTMLAudioElement} audioElement - 要重置的音频元素
 */
function resetAudioElement(audioElement) {
    try {
        // 暂停播放
        audioElement.pause();
        
        // 重置时间
        audioElement.currentTime = 0;
        
        // 移除所有事件监听器
        const newAudioElement = audioElement.cloneNode(true);
        const parent = audioElement.parentNode;
        if (parent) {
            parent.replaceChild(newAudioElement, audioElement);
            // 更新DOM引用
            DOM.voicePlayer = newAudioElement;
        }
        
        console.log('音频元素已成功重置');
    } catch (e) {
        console.warn('重置音频元素时出错:', e);
        // 即使出错，也要尝试基本清理
        audioElement.pause();
        audioElement.currentTime = 0;
    }
}

/**
 * 连接音频分析器
 * returns {boolean} 是否成功连接
 */
function connectAudioAnalyser() {
    try {
        if (!AppState.audioContext || !AppState.analyser || !DOM.voicePlayer) {
            console.warn('音频上下文、分析器或播放器未初始化');
            return false;
        }
        
        // 确保音频上下文处于运行状态
        if (AppState.audioContext.state === 'suspended') {
            AppState.audioContext.resume().catch(e => console.warn('恢复音频上下文失败:', e));
        }
        
        // 彻底清理之前的音频源连接
        if (AppState.audioSource) {
            try {
                AppState.audioSource.disconnect();
            } catch (e) {
                console.warn('断开旧音频源连接时出错:', e);
            }
            AppState.audioSource = null;
        }
        
        // 策略1: 尝试直接创建新的媒体元素源
        try {
            AppState.audioSource = AppState.audioContext.createMediaElementSource(DOM.voicePlayer);
        } catch (innerError) {
            console.warn('策略1失败，尝试策略2:', innerError);
            
            // 策略2: 创建新的AudioContext
            try {
                // 先完全清理当前的audioContext
                if (AppState.audioContext) {
                    try {
                        AppState.audioContext.close();
                    } catch (e) {
                        console.warn('关闭旧音频上下文时出错:', e);
                    }
                }
                
                // 创建新的AudioContext
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                AppState.audioContext = new AudioContext();
                AppState.analyser = AppState.audioContext.createAnalyser();
                AppState.analyser.fftSize = 256;
                AppState.analyser.smoothingTimeConstant = 0.3;
                
                // 再次尝试创建媒体元素源
                AppState.audioSource = AppState.audioContext.createMediaElementSource(DOM.voicePlayer);
            } catch (fallbackError) {
                console.warn('策略2也失败，尝试终极策略:', fallbackError);
                
                // 终极策略: 重置整个音频系统
                try {
                    // 完全重置DOM中的音频元素
                    resetAudioElement(DOM.voicePlayer);
                    
                    // 创建全新的AudioContext
                    if (AppState.audioContext) {
                        try {
                            AppState.audioContext.close();
                        } catch (e) {}
                    }
                    const AudioContext = window.AudioContext || window.webkitAudioContext;
                    AppState.audioContext = new AudioContext();
                    AppState.analyser = AppState.audioContext.createAnalyser();
                    AppState.analyser.fftSize = 256;
                    AppState.analyser.smoothingTimeConstant = 0.3;
                    
                    // 最后尝试创建媒体元素源
                    AppState.audioSource = AppState.audioContext.createMediaElementSource(DOM.voicePlayer);
                } catch (ultimateError) {
                    console.error('所有连接策略均失败:', ultimateError);
                    return false;
                }
            }
        }
        
        // 连接分析器和输出
        try {
            AppState.audioSource.connect(AppState.analyser);
            AppState.analyser.connect(AppState.audioContext.destination);
        } catch (connectError) {
            console.error('连接分析器或输出时出错:', connectError);
            // 清理已创建但未成功连接的音频源
            if (AppState.audioSource) {
                AppState.audioSource.disconnect();
                AppState.audioSource = null;
            }
            return false;
        }
        
        return true;
    } catch (error) {
        console.error('连接音频分析器失败:', error);
        return false;
    }
}

/**
 * 开始口型同步
 */
function startMouthShapeSync() {
    // 清除之前的动画帧
    if (AppState.animationFrameId) {
        cancelAnimationFrame(AppState.animationFrameId);
    }
    
    // 动画循环
    function animateMouth() {
        if (!AppState.isVoicePlaying) {
            return; // 停止动画
        }
        
        // 计算口型值
        const mouthValue = calculateMouthShape();
        
        // 更新模型口型
        updateModelMouthShape(mouthValue);
        
        // 继续动画
        AppState.animationFrameId = requestAnimationFrame(animateMouth);
    }
    
    // 开始动画
    animateMouth();
}

/**
 * 计算口型值
 */
function calculateMouthShape() {
    // 如果有分析器，使用音频分析，否则使用模拟值
    return AppState.analyser ? calculateMouthShapeFromAudio() : generateSimulatedMouthValue();
}

/**
 * 从音频计算口型值
 */
function calculateMouthShapeFromAudio() {
    try {
        if (!AppState.analyser) return 0;
        
        const bufferLength = AppState.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        
        // 获取频率数据
        AppState.analyser.getByteFrequencyData(dataArray);
        
        // 计算音频能量（主要关注中高频，对应语音）
        let sum = 0;
        let count = 0;
        
        // 只考虑中高频部分（索引20-80）
        const startIdx = Math.min(20, bufferLength);
        const endIdx = Math.min(80, bufferLength);
        
        for (let i = startIdx; i < endIdx; i++) {
            sum += dataArray[i];
            count++;
        }
        
        // 计算平均值并归一化到0-1范围
        const average = count > 0 ? sum / count : 0;
        const normalizedValue = Math.min(1, average / 128); // 归一化到0-1
        
        // 应用非线性映射使口型变化更自然
        return Math.pow(normalizedValue, 1.5); // 指数曲线增强效果
        
    } catch (error) {
        console.error('计算口型值失败:', error);
        return generateSimulatedMouthValue();
    }
}

/**
 * 生成模拟口型值（备用方案）
 */
function generateSimulatedMouthValue() {
    // 使用正弦函数和随机因素生成自然的模拟值
    const time = Date.now() / 1000;
    const baseValue = (Math.sin(time * 2.5) + 1) / 2; // 基础波动（0-1）
    const randomFactor = Math.random() * 0.2; // 随机因素
    
    return Math.min(1, baseValue * 0.7 + randomFactor); // 限制最大值并调整幅度
}

/**
 * 更新模型口型
 */
function updateModelMouthShape(value) {
    try {
        if (!AppState.model) {
            console.warn('模型未初始化');
            return;
        }
        
        // 确保值在有效范围内
        const normalizedValue = Math.max(0, Math.min(1, value));
        
        // 更新模型口型参数
        if (AppState.model.internalModel && AppState.model.internalModel.coreModel) {
            AppState.model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', normalizedValue);
        }
        
    } catch (error) {
        console.error('更新口型失败:', error);
    }
}

/**
 * 播放失败时的备用口型动画
 */
function fallbackMouthAnimation() {
    let animationCount = 0;
    const maxAnimations = 30; // 动画持续时间
    
    function animate() {
        if (animationCount >= maxAnimations) {
            updateModelMouthShape(0); // 重置口型
            return;
        }
        
        // 生成模拟口型值
        const progress = animationCount / maxAnimations;
        const mouthValue = 0.3 + 0.5 * Math.sin(progress * Math.PI * 4); // 波动的口型值
        
        updateModelMouthShape(mouthValue);
        animationCount++;
        
        requestAnimationFrame(animate);
    }
    
    animate();
}

/**
 * 清理语音播放资源
 */
function cleanupVoicePlayback() {
    // 停止口型同步
    AppState.isVoicePlaying = false;
    
    // 清除动画帧
    if (AppState.animationFrameId) {
        cancelAnimationFrame(AppState.animationFrameId);
        AppState.animationFrameId = null;
    }
    
    // 重置口型
    updateModelMouthShape(0);
    
    // 断开音频源连接 - 这很重要，可以防止"already connected"错误
    if (AppState.audioSource) {
        try {
            AppState.audioSource.disconnect();
        } catch (e) {
            console.warn('断开音频源连接时出错:', e);
        }
        AppState.audioSource = null;
    }
    
    // 延迟释放音频URL，确保在所有操作完成后再释放
    if (AppState.activeAudioUrl) {
        // 使用setTimeout确保在当前事件循环结束后再释放资源
        setTimeout(() => {
            try {
                URL.revokeObjectURL(AppState.activeAudioUrl);
            } catch (e) {
                console.warn('释放音频URL时出错:', e);
            }
            AppState.activeAudioUrl = null;
        }, 500); // 延迟500ms释放，确保音频播放完全结束
    }
}

/**
 * 重置语音状态
 */
function resetVoiceState() {
    // 停止播放并重置时间
    if (DOM.voicePlayer) {
        DOM.voicePlayer.pause();
        DOM.voicePlayer.currentTime = 0;
    }
    
    // 重置状态
    cleanupVoicePlayback();
}

// 等待DOM加载完成后初始化应用
document.addEventListener('DOMContentLoaded', initApp);
// Web_Gal 角色互动系统

// 集中管理应用的核心状态和资源
const AppState = {
    // 音频相关状态
    isVoicePlaying: false,
    audioContext: null,
    analyser: null,
    audioSource: null,
    activeAudioUrl: null,
    currentPlayingAudioUrl: null, // 当前正在播放的音频URL
    
    // 模型相关状态
    model: null,
    app: null,
    
    // 动画状态
    animationFrameId: null,
    
    // 表情相关状态
    currentExpression: null,
    expressionQueue: [],
    
    // 新增：表情与语音分段处理相关状态
    isProcessingSequence: false,
    currentSequenceIndex: 0,
    dialogueSequence: [],
    
    // 新增：TTS音频预加载缓存
    ttsAudioCache: new Map()
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
    const modelPath = '/live2d_assets/nahida/草神.model3.json'; 
    try {
        console.log('尝试加载Live2D模型:', modelPath);
        
        // 加载模型
        const model = await Live2DModel.from(modelPath, {autoInteract: false});
        console.log('Live2D模型加载成功:', modelPath);
        return model;
        
    } catch (error) {
        console.warn('Live2D模型加载失败:', error);
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
        targetX = -nx * 60; // 左右最大 60°
        targetY = -ny * 60; // 上下最大 60°
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
 * 将文本按照表情标签分段，创建表情与语音的序列
 * @param {string} text - 包含表情标签的文本
 * @returns {Array} - 包含表情和对应文本的序列数组
 */
function createDialogueSequence(text) {
    const sequence = [];
    let currentText = '';
    let index = 0;
    
    // 默认开始时没有表情
    let currentEmotion = null;
    
    while (index < text.length) {
        if (text.charAt(index) === '[') {
            // 找到表情标签的开始
            const endIndex = text.indexOf(']', index);
            if (endIndex !== -1) {
                // 提取标签内容
                const emotionTag = text.substring(index + 1, endIndex);
                
                // 如果当前有累积的文本，将其添加到序列中
                if (currentText.trim() !== '') {
                    sequence.push({
                        emotion: currentEmotion,
                        text: currentText.trim()
                    });
                    currentText = '';
                }
                
                // 设置当前表情
                currentEmotion = emotionTag;
                
                // 跳过整个标签
                index = endIndex + 1;
            } else {
                // 没有找到对应的结束标签，正常处理字符
                currentText += text.charAt(index);
                index++;
            }
        } else {
            // 正常处理字符
            currentText += text.charAt(index);
            index++;
        }
    }
    
    // 添加最后一段文本（如果有）
    if (currentText.trim() !== '') {
        sequence.push({
            emotion: currentEmotion,
            text: currentText.trim()
        });
    }
    
    return sequence;
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
        
        // 创建对话序列
        const sequence = createDialogueSequence(reply);
        
        // 如果序列为空，直接显示原文本
        if (sequence.length === 0) {
            DOM.dialogue.textContent = reply;
            return;
        }
        
        // 设置序列状态
        AppState.dialogueSequence = sequence;
        AppState.currentSequenceIndex = 0;
        AppState.isProcessingSequence = true;
        
        try {
            // 等待所有序列项的TTS音频预加载完成，再开始处理序列
            await preloadAllTTSAudio(sequence);
                    
            // 清空对话框
            DOM.dialogue.textContent = '';

            // 预加载完成后开始处理序列
            processNextSequenceItem();
        } catch (preloadError) {
            console.error('音频预加载过程中发生错误:', preloadError);
            // 即使预加载失败也继续处理序列

            // 清空对话框
            DOM.dialogue.textContent = '';

            processNextSequenceItem();
        }
        
    } catch (error) {
        console.error('处理对话失败:', error);
        DOM.dialogue.textContent = '出错了，请稍后再试。';
        AppState.isProcessingSequence = false;
    }
}

/**
 * 打字机效果函数
 * 使文本一个字一个字地显示出来，同时支持表情标签触发
 * @param {HTMLElement} element - 要显示文本的DOM元素
 * @param {string} text - 要显示的文本内容
 * @param {boolean} append - 是否追加到现有内容后面
 * @param {number} speed - 每个字之间的延迟时间（毫秒）
 */
function typewriterEffect(element, text, append = false, speed = 50) {
    return new Promise(resolve => {
        if (!element) {
            resolve();
            return;
        }
        
        // 用于调试：在UI中显示表情标签
        let displayText = text;
        
        let index = 0;
        // 保存初始文本（如果是追加模式）
        const initialText = append ? element.textContent : '';
        // 如果不是追加模式，清空元素
        if (!append) {
            element.textContent = '';
        }
        
        function typeNext() {
            if (index < displayText.length) {
                // 检查当前字符是否是表情标签的开始
                if (displayText.charAt(index) === '[') {
                    // 尝试找到对应的结束标签
                    const endIndex = displayText.indexOf(']', index);
                    if (endIndex !== -1) {
                        const tagContent = displayText.substring(index + 1, endIndex);
                        const fullTag = displayText.substring(index, endIndex + 1);
                        
                        // 直接显示完整的标签
                        element.textContent = initialText + displayText.substring(0, index) + fullTag;
                        index = endIndex + 1;
                        
                        // 触发表情应用
                        AppState.expressionQueue.push(tagContent);
                        checkAndApplyNextExpression();
                    } else {
                        // 没有找到对应的结束标签，正常显示字符
                        element.textContent = initialText + displayText.substring(0, index + 1);
                        index++;
                    }
                } else {
                    // 正常显示字符
                    element.textContent = initialText + displayText.substring(0, index + 1);
                    index++;
                }
                
                // 检查并应用队列中的表情
                if (AppState.expressionQueue.length > 0) {
                    checkAndApplyNextExpression();
                }
                
                // 设置下一个字符的定时器
                setTimeout(typeNext, speed);
            } else {
                // 文本显示完成，检查是否有剩余的表情需要应用
                if (AppState.expressionQueue.length > 0) {
                    // 应用剩余的表情
                    applyExpression(AppState.expressionQueue[AppState.expressionQueue.length - 1]);
                }
                
                // 解析Promise
                resolve();
            }
        }
        
        // 检查并应用队列中的下一个表情
        function checkAndApplyNextExpression() {
            if (AppState.expressionQueue.length > 0) {
                const nextExpression = AppState.expressionQueue.shift();
                applyExpression(nextExpression);
            }
        }
        
        // 开始打字效果
        typeNext();
    });
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
 * 预加载所有序列项的TTS音频
 * @param {Array} sequence - 对话序列
 * @returns {Promise} - 返回预加载完成的Promise
 */
async function preloadAllTTSAudio(sequence) {
    // 获取当前序列需要的文本内容
    const neededTexts = new Set(sequence.map(item => item.text));
    
    // 只保留当前序列需要的缓存，移除其他缓存以释放内存
    for (const key of AppState.ttsAudioCache.keys()) {
        if (!neededTexts.has(key)) {
            AppState.ttsAudioCache.delete(key);
        }
    }
    
    // 并发预加载所有需要但尚未缓存的音频
    const preloadPromises = sequence.map(item => {
        // 检查是否已经在缓存中
        if (AppState.ttsAudioCache.has(item.text)) {
            console.log(`使用已缓存的TTS音频: ${item.text.substring(0, 20)}...`);
            return Promise.resolve();
        }
        
        return fetchTTSAudio(item.text).then(blob => {
            // 缓存预加载的音频数据
            AppState.ttsAudioCache.set(item.text, blob);
            console.log(`成功预加载TTS音频: ${item.text.substring(0, 20)}...`);
        }).catch(error => {
            console.warn(`预加载TTS音频失败: ${error.message}`);
            // 即使失败也不阻止程序继续运行
        });
    });
    
    // 等待所有预加载完成
    await Promise.all(preloadPromises);
    console.log('所有TTS音频预加载完成');
    
    return Promise.resolve();
}

/**
 * 播放语音
 */
async function playVoice(text) {
    // 返回Promise，确保函数能够正确等待语音播放完成
    return new Promise((resolve, reject) => {
        // 重置之前的状态，但不释放资源
        resetVoiceState(false);
        
        if (!DOM.voicePlayer) {
            console.error('语音播放器元素不存在');
            fallbackMouthAnimation(); // 即使没有播放器也显示口型动画
            resolve(); // 确保Promise被解析
            return;
        }
        
        try {
            // 首先检查是否有预加载的音频数据
            const cachedAudio = AppState.ttsAudioCache.get(text);
            
            if (cachedAudio) {
                console.log('使用预加载的TTS音频');
                processAudioData(cachedAudio);
            } else {
                console.log('请求TTS音频...');
                // 如果没有预加载，则请求TTS服务获取语音
                fetchTTSAudio(text).then(blob => {
                    processAudioData(blob);
                }).catch(error => {
                    console.error('获取TTS音频失败:', error);
                    // 确保即使在错误情况下也正确清理资源
                    setTimeout(() => {
                        resetVoiceState();
                        fallbackMouthAnimation();
                        resolve(); // 确保Promise被解析
                    }, 100);
                });
            }
            
            // 处理音频数据的辅助函数
            function processAudioData(blob) {
                // 检查获取的blob是否有效
                if (!blob || blob.size === 0) {
                    throw new Error('获取到的音频数据为空');
                }
                
                // 完全重置音频元素
                resetAudioElement(DOM.voicePlayer);
                
                // 创建音频URL
                const audioUrl = URL.createObjectURL(blob);
                AppState.activeAudioUrl = audioUrl;
                
                // 设置音频源（必须在重置元素后设置）
                DOM.voicePlayer.src = audioUrl;
                
                // 存储当前播放的音频URL，避免被过早释放
                AppState.currentPlayingAudioUrl = audioUrl;
                
                // 连接音频分析器
                if (!connectAudioAnalyser()) {
                    console.warn('音频分析器连接失败，将使用模拟口型动画');
                }
                
                // 预加载音频
                DOM.voicePlayer.load();
                
                // 播放结束后清理
                DOM.voicePlayer.onended = function() {
                    // 确保在清理前等待一小段时间
                    setTimeout(() => {
                        cleanupVoicePlayback(audioUrl); // 传递具体的audioUrl
                        resolve(); // 播放完成后解析Promise
                    }, 100);
                };
                
                // 错误处理
                DOM.voicePlayer.onerror = function(error) {
                    console.error('音频播放错误:', error);
                    cleanupVoicePlayback(audioUrl); // 传递具体的audioUrl
                    fallbackMouthAnimation(); // 显示备用口型动画
                    resolve(); // 即使失败也解析Promise，避免阻塞
                };
                
                // 开始播放语音
                DOM.voicePlayer.play().then(() => {
                    AppState.isVoicePlaying = true;
                    
                    // 开始口型同步或使用备用动画
                    if (AppState.analyser) {
                        startMouthShapeSync();
                    } else {
                        fallbackMouthAnimation();
                    }
                }).catch(error => {
                    console.error('播放语音失败:', error);
                    // 确保即使在错误情况下也正确清理资源
                    setTimeout(() => {
                        resetVoiceState();
                        fallbackMouthAnimation();
                        resolve(); // 确保Promise被解析
                    }, 100);
                });
            }
        } catch (error) {
            console.error('播放语音过程中发生异常:', error);
            // 确保即使在错误情况下也正确清理资源
            setTimeout(() => {
                resetVoiceState();
                fallbackMouthAnimation();
                resolve(); // 确保Promise被解析
            }, 100);
        }
    });
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
        
        // 控制口型最大张开程度 - 限制为原来的60%
        const maxMouthOpenScale = 0.6; // 可以调整这个值来控制口型的最大张开程度
        const scaledValue = normalizedValue * maxMouthOpenScale;
        
        // 更新模型口型参数
        if (AppState.model.internalModel && AppState.model.internalModel.coreModel) {
            AppState.model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', scaledValue);
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
 * @param {string} audioUrl - 要释放的特定音频URL，可选
 */
function cleanupVoicePlayback(audioUrl) {
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
    
    // 只有当明确提供了audioUrl且与当前播放的URL匹配时，才清除当前播放的URL引用
    if (audioUrl && audioUrl === AppState.currentPlayingAudioUrl) {
        AppState.currentPlayingAudioUrl = null;
    }
    
    // 延迟释放音频URL，确保在所有操作完成后再释放
    if (audioUrl) {
        // 使用setTimeout确保在当前事件循环结束后再释放资源
        setTimeout(() => {
            // 再次检查这个URL是否正在被其他播放使用
            if (audioUrl !== AppState.currentPlayingAudioUrl) {
                try {
                    URL.revokeObjectURL(audioUrl);
                    console.log('成功释放音频URL');
                } catch (e) {
                    console.warn('释放音频URL时出错:', e);
                }
            }
        }, 500); // 增加延迟时间到500ms，确保音频播放完全结束并且不会影响后续播放
    }
    
    // 清除AppState中的activeAudioUrl引用
    AppState.activeAudioUrl = null;
}

/**
 * 处理下一个对话序列项
 */
async function processNextSequenceItem() {
    if (!AppState.isProcessingSequence || !AppState.dialogueSequence) {
        return;
    }
    
    // 检查是否处理完所有序列项
    if (AppState.currentSequenceIndex >= AppState.dialogueSequence.length) {
        AppState.isProcessingSequence = false;
        AppState.dialogueSequence = null;
        return;
    }
    
    try {
        // 获取当前序列项
        const currentItem = AppState.dialogueSequence[AppState.currentSequenceIndex];
        
        console.log(`处理序列项 ${AppState.currentSequenceIndex + 1}/${AppState.dialogueSequence.length}`, currentItem);
        
        // 如果有表情，应用表情
        if (currentItem.emotion) {
            applyExpression(currentItem.emotion);
        }

        // 并行执行打字机效果和语音播放，减少用户感知的延迟
        const typewriterPromise = typewriterEffect(DOM.dialogue, currentItem.text + ' ', true);
        const voicePromise = playVoice(currentItem.text);

        // 等待两者都完成
        await Promise.all([typewriterPromise, voicePromise]);
        
        // 移动到下一个序列项
        AppState.currentSequenceIndex++;
        
        // 递归处理下一个序列项 - 使用setTimeout确保当前的调用栈完成
        setTimeout(processNextSequenceItem, 10);
        
    } catch (error) {
        console.error('处理序列项失败:', error);
        AppState.isProcessingSequence = false;
        // 显示错误消息，但保留已显示的文本
        DOM.dialogue.textContent += ' [处理对话时出错]';
    }
}

/**
 * 应用表情到Live2D模型
 * @param {string} emotionTag - 表情标签名称
 */

function resetExpression() {
    const core = AppState.model.internalModel.coreModel;
    if (!core) {
        console.error('模型核心不存在，无法重置表情');
        return;
    }
    
    // 重置所有表情相关参数
    try {
        core.setParameterValueById('Param43', 0);
        core.setParameterValueById('Param54', 0);
        core.setParameterValueById('Param57', 0);
        core.setParameterValueById('Param55', 0);
        core.setParameterValueById('Param44', 0);
        core.setParameterValueById('Param59', 0);
        core.setParameterValueById('Param42', 0);
        core.setParameterValueById('Param56', 0);
        core.setParameterValueById('Param60', 0);
        core.setParameterValueById('Param58', 0);
        core.saveParameters();
    } catch (error) {
        console.error('重置表情参数失败:', error);
    }
}

function applyExpression(emotionTag) {
    if (!AppState.model || !AppState.model.internalModel || !AppState.model.internalModel.coreModel) {
        console.warn('模型未初始化，无法应用表情');
        return;
    }
    
    const core = AppState.model.internalModel.coreModel;
    
    // 如果标签为空，重置表情
    if (!emotionTag || emotionTag.trim() === '') {
        // 重置所有表情相关参数
        try {
            resetExpression();
            AppState.currentExpression = null;
            console.log('表情已重置');
        } catch (error) {
            console.error('重置表情失败:', error);
        }
        return;
    }
    
    // 根据标签应用不同的表情
    try {
        console.log(`尝试应用表情: ${emotionTag}`);
        
        // 先重置表情，确保没有残留效果
        resetExpression();
        
        switch (emotionTag) {
            case '脸红':
                core.setParameterValueById('Param43', 30);
                console.log('应用表情成功: 脸红 (Param43 = 30)');
                break;
            case '生气':
                core.setParameterValueById('Param54', 30);
                console.log('应用表情成功: 生气 (Param54 = 30)');
                break;
            case '好奇':
                core.setParameterValueById('Param57', 30);
                console.log('应用表情成功: 好奇 (Param57 = 30)');
                break;
            case '泪':
                core.setParameterValueById('Param55', 30);
                console.log('应用表情成功: 泪 (Param55 = 30)');
                break;
            case '星星':
                core.setParameterValueById('Param44', 30);
                console.log('应用表情成功: 星星 (Param44 = 30)');
                break;
            case '发光':
                core.setParameterValueById('Param59', 30);
                console.log('应用表情成功: 发光 (Param59 = 30)');
                break;
            case '脸黑':
                core.setParameterValueById('Param42', 30);
                console.log('应用表情成功: 脸黑 (Param42 = 30)');
                break;
            case '祈祷':
                core.setParameterValueById('Param56', 30);
                core.setParameterValueById('Param60', 30);
                console.log('应用表情成功: 祈祷 (Param56 = 30, Param60 = 30)');
                break;
            case '翻花绳':
                core.setParameterValueById('Param58', 30);
                console.log('应用表情成功: 翻花绳 (Param58 = 30)');
                break;
            default:
                console.log('未知表情标签:', emotionTag);
                return;
        }
        
        // 保存参数确保表情生效
        core.saveParameters();
        AppState.currentExpression = emotionTag;
        
        // 添加一个小延迟确保表情有足够时间渲染
        setTimeout(() => {
            console.log(`表情${emotionTag}渲染完成`);
        }, 100);
        
    } catch (error) {
        console.error(`应用表情${emotionTag}失败:`, error);
        // 尝试获取所有可用参数，用于调试
        try {
            console.log('当前可用参数:');
            for (let i = 0; i < Math.min(core.getParameterCount(), 10); i++) {
                const id = core.getParameterId(i);
                const value = core.getParameterValueById(id);
                console.log(`${id}: ${value}`);
            }
        } catch (innerError) {
            console.warn('获取参数信息失败:', innerError);
        }
    }
}

/**
 * 重置语音状态
 * @param {boolean} releaseResources - 是否释放音频资源，默认为false
 */
function resetVoiceState(releaseResources = false) {
    // 停止播放并重置时间
    if (DOM.voicePlayer) {
        DOM.voicePlayer.pause();
        DOM.voicePlayer.currentTime = 0;
    }
    
    // 只在明确需要释放资源时调用cleanupVoicePlayback
    if (releaseResources) {
        cleanupVoicePlayback(AppState.activeAudioUrl);
    }
}

// 等待DOM加载完成后初始化应用
document.addEventListener('DOMContentLoaded', initApp);
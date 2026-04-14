// Web_Gal 角色互动系统

// 集中管理应用的核心状态和资源
const AppState = {
    isVoicePlaying: false,
    audioContext: null,
    analyser: null,
    audioSource: null,
    activeAudioUrl: null,
    currentPlayingAudioUrl: null,
    model: null,
    app: null,
    animationFrameId: null,
    currentExpression: null,
    expressionQueue: [],
    isProcessingSequence: false,
    currentSequenceIndex: 0,
    dialogueSequence: [],
    ttsAudioCache: new Map(),
    ttsFailedTexts: new Set(),
    isWaitingForAudio: false,
    isAgentMode: false,
    currentToolCalls: [],
    chatHistory: []
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
    submitBtn: null,
    optionAgent: null,
    optionToken: null,
    optionLog: null,
    toolCallDisplay: null,
    tokenPanel: null,
    logPanel: null,
    logContent: null,
    tokenPrompt: null,
    tokenCompletion: null,
    tokenTotal: null
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
        initModeSwitch();
        initLogPanel();

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
    DOM.optionAgent = document.getElementById('option-agent');
    DOM.optionToken = document.getElementById('option-token');
    DOM.optionLog = document.getElementById('option-log');
    DOM.toolCallDisplay = document.getElementById('tool-call-display');
    DOM.tokenPanel = document.getElementById('token-panel');
    DOM.logPanel = document.getElementById('log-panel');
    DOM.logContent = document.getElementById('log-content');
    DOM.tokenPrompt = document.getElementById('token-prompt');
    DOM.tokenCompletion = document.getElementById('token-completion');
    DOM.tokenTotal = document.getElementById('token-total');
}

function toggleAgentMode() {
    AppState.isAgentMode = !AppState.isAgentMode;
    updateAgentUI();
}

function updateAgentUI() {
    if (AppState.isAgentMode) {
        DOM.optionAgent.classList.add('active');
        if (DOM.toolCallDisplay) {
            DOM.toolCallDisplay.classList.add('show');
        }
    } else {
        DOM.optionAgent.classList.remove('active');
        if (DOM.toolCallDisplay) {
            DOM.toolCallDisplay.classList.remove('show');
        }
    }
}

function showTokenInfo() {
    if (DOM.tokenPanel) {
        DOM.tokenPanel.classList.remove('hidden');
    }
}

function hideTokenInfo() {
    if (DOM.tokenPanel) {
        DOM.tokenPanel.classList.add('hidden');
    }
}

function updateTokenDisplay(usage) {
    if (!usage) return;
    if (DOM.tokenPrompt) DOM.tokenPrompt.textContent = usage.prompt_tokens || 0;
    if (DOM.tokenCompletion) DOM.tokenCompletion.textContent = usage.completion_tokens || 0;
    if (DOM.tokenTotal) DOM.tokenTotal.textContent = usage.total_tokens || 0;
}

function toggleLogPanel() {
    if (DOM.logPanel) {
        DOM.logPanel.classList.toggle('hidden');
        if (!DOM.logPanel.classList.contains('hidden')) {
            renderChatHistory();
        }
    }
}

function initModeSwitch() {
    AppState.isAgentMode = false;
    updateAgentUI();
}

function initLogPanel() {
    if (!DOM.logPanel) return;

    DOM.logPanel.addEventListener('click', (e) => {
        if (e.target === DOM.logPanel) {
            DOM.logPanel.classList.add('hidden');
        }
    });
}

function addToChatHistory(role, content) {
    AppState.chatHistory.push({
        role,
        content,
        time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    });
}

function renderChatHistory() {
    if (!DOM.logContent) return;

    if (AppState.chatHistory.length === 0) {
        DOM.logContent.innerHTML = '<p style="color: #6b8e6b; text-align: center;">暂无历史记录</p>';
        return;
    }

    let html = '';
    for (const item of AppState.chatHistory) {
        const roleLabel = item.role === 'user' ? '用户' : '纳西妲';
        html += `
            <div class="log-item ${item.role}">
                <div class="role">${roleLabel}</div>
                <div class="content">${escapeHtml(item.content)}</div>
                <div class="time">${item.time}</div>
            </div>
        `;
    }
    DOM.logContent.innerHTML = html;
    DOM.logContent.scrollTop = DOM.logContent.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function displayToolCalls(toolCalls) {
    if (!toolCalls || toolCalls.length === 0) {
        if (DOM.toolCallDisplay) DOM.toolCallDisplay.classList.remove('show');
        return;
    }

    if (!DOM.toolCallDisplay) return;
    DOM.toolCallDisplay.classList.add('show');
    let html = '<ul>';

    for (const call of toolCalls) {
        const toolName = call.tool;
        const args = call.args || {};
        const result = call.result || {};

        let resultClass = 'tool-result';
        let resultText = '';

        if (result.success === false) {
            resultClass += ' error';
            resultText = result.error || '执行失败';
        } else if (result.content) {
            resultText = typeof result.content === 'string'
                ? result.content.substring(0, 200)
                : JSON.stringify(result.content).substring(0, 200);
        } else if (result.items) {
            resultText = `${result.items.length} 个项目`;
        } else if (result.output) {
            resultText = result.output.substring(0, 200);
        } else {
            resultText = '执行成功';
        }

        html += `
            <li>
                <span class="tool-name">${toolName}</span>
                <div class="tool-result ${resultClass}">${escapeHtml(resultText)}</div>
            </li>
        `;
    }

    html += '</ul>';
    DOM.toolCallDisplay.innerHTML = html;
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

    addToChatHistory('user', inputText);
    DOM.userInput.value = '';
    DOM.dialogue.textContent = '思考中……';

    try {
        const agentMode = AppState.isAgentMode;

        if (agentMode) {
            const result = await handleAgentModeStream(inputText);
            addToChatHistory('assistant', result.reply);
        } else {
            const data = await getAIReply(inputText, agentMode);
            const reply = data.reply || '';
            const toolCalls = data.tool_calls || [];
            const usage = data.usage;

            addToChatHistory('assistant', reply);
            if (data.mode === 'agent' !== AppState.isAgentMode) {
                AppState.isAgentMode = data.mode === 'agent';
                updateAgentUI();
            }
            displayToolCalls(toolCalls);

            if (usage) {
                updateTokenDisplay(usage);
            }

            const sequence = createDialogueSequence(reply);
            if (sequence.length === 0) {
                DOM.dialogue.textContent = reply;
                return;
            }

            AppState.dialogueSequence = sequence;
            AppState.currentSequenceIndex = 0;
            AppState.isProcessingSequence = true;
            DOM.dialogue.textContent = '';
            prepareNextAudio(0);
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
function typewriterEffect(element, text, append = false, speed = 50, emotion = null) {
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
        
        // 在显示第一个字时触发表情
        let emotionTriggered = false;
        
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

                    // 在显示第一个字时触发表情
                    if (!emotionTriggered && emotion) {
                        emotionTriggered = true;
                        applyExpression(emotion);
                    }
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
async function getAIReply(message, agentMode) {
    try {
        const history = AppState.chatHistory.map(item => ({
            role: item.role,
            content: item.content
        }));

        const response = await fetch('/api/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, agent: agentMode, history })
        });

        if (!response.ok) {
            throw new Error(`API请求失败: ${response.status}`);
        }

        return await response.json();

    } catch (error) {
        console.error('获取AI回复失败:', error);
        throw error;
    }
}

/**
 *  Agent模式流式处理
 */
async function handleAgentModeStream(message) {
    const streamState = {
        toolCalls: [],
        accumulatedReply: '',
        pendingText: '',
        hasError: false
    };

    try {
        const history = AppState.chatHistory.map(item => ({
            role: item.role,
            content: item.content
        }));

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, agent: true, history })
        });

        if (!response.ok) {
            throw new Error(`API请求失败: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        AppState.isAgentMode = true;
        updateAgentUI();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const data = line.slice(6);
                if (!data.trim()) continue;

                try {
                    const event = JSON.parse(data);
                    handleStreamEvent(event, streamState);
                } catch (e) {
                    console.warn('解析流事件失败:', e);
                }
            }
        }

        if (streamState.pendingText) {
            DOM.dialogue.textContent += streamState.pendingText;
        }

        if (streamState.hasError) {
            throw new Error('Agent模式处理失败');
        }

        return { reply: streamState.accumulatedReply, toolCalls: streamState.toolCalls };

    } catch (error) {
        console.error('Agent模式流式处理失败:', error);
        throw error;
    }
}

function handleStreamEvent(event, state) {
    const { type, content, tool, args, tool_calls, message } = event;

    if (type === 'error') {
        console.error('流式处理错误:', message);
        state.hasError = true;
        DOM.dialogue.textContent = `\n[错误: ${message}]`;
        return;
    }

    if (type === 'partial') {
        state.accumulatedReply = content;
        state.pendingText = '';
        const result = processContentWithEmotions(content, '');
        DOM.dialogue.textContent = result.display;
    }

    if (type === 'final') {
        state.accumulatedReply = content;
    }

    if (type === 'tool_call') {
        state.toolCalls.push({ tool, args, result: {} });
        updateToolCallDisplay(state.toolCalls);
    }

    if (type === 'done') {
        updateToolCallDisplay(tool_calls || state.toolCalls);
        const finalText = state.accumulatedReply;
        const usage = event.usage;
        if (usage) {
            updateTokenDisplay(usage);
        }
        if (finalText) {
            const sequence = createDialogueSequence(finalText);
            if (sequence.length > 0) {
                AppState.dialogueSequence = sequence;
                AppState.currentSequenceIndex = 0;
                AppState.isProcessingSequence = true;
                DOM.dialogue.textContent = '';
                prepareNextAudio(0);
                processNextSequenceItem();
            }
        }
    }
}

function processContentWithEmotionsForElement(text) {
    const emotionRegex = /\[([^\]]+)\]/g;
    let match;
    while ((match = emotionRegex.exec(text)) !== null) {
        applyExpression(match[1]);
    }
}

const VALID_EMOTION_TAGS = ['祈祷', '发光', '翻花绳', '好奇', '泪', '脸黑', '脸红', '生气', '星星'];

function isValidEmotionTag(tag) {
    return VALID_EMOTION_TAGS.includes(tag);
}

function processContentWithEmotions(text, pending) {
    const fullText = pending + text;
    const emotionRegex = /\[([^\]]+)\]/g;
    let lastIndex = 0;
    let match;
    let display = '';
    let pendingText = '';

    while ((match = emotionRegex.exec(fullText)) !== null) {
        if (match.index > lastIndex) {
            display += fullText.slice(lastIndex, match.index);
        }
        if (isValidEmotionTag(match[1])) {
            applyExpression(match[1]);
        } else {
            display += match[0];
        }
        lastIndex = emotionRegex.lastIndex;
    }

    if (lastIndex < fullText.length) {
        const remaining = fullText.slice(lastIndex);
        const openBracket = remaining.lastIndexOf('[');
        if (openBracket !== -1 && !remaining.includes(']')) {
            display += remaining.slice(0, openBracket);
            pendingText = remaining.slice(openBracket);
        } else {
            display += remaining;
            pendingText = '';
        }
    } else {
        pendingText = '';
    }

    return { display, pending: pendingText };
}

function updateToolCallDisplay(toolCalls) {
    displayToolCalls(toolCalls);
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

function prepareNextAudio(index, count = 3) {
    const sequence = AppState.dialogueSequence;
    if (!sequence) return;

    for (let i = 0; i < count && index + i < sequence.length; i++) {
        const item = sequence[index + i];
        if (!item || !item.text || !item.text.trim()) continue;
        if (AppState.ttsAudioCache.has(item.text)) continue;
        if (AppState.ttsFailedTexts.has(item.text)) continue;

        fetchTTSAudio(item.text).then(blob => {
            AppState.ttsAudioCache.set(item.text, blob);
            console.log(`后台预载TTS音频完成: ${item.text.substring(0, 20)}...`);
        }).catch(error => {
            console.warn(`后台预载TTS音频失败: ${error.message}`);
            AppState.ttsFailedTexts.add(item.text);
        });
    }
}

/**
 * 播放语音
 */
async function playVoice(text) {
    return new Promise((resolve) => {
        resetVoiceState(false);

        if (!DOM.voicePlayer) {
            fallbackMouthAnimation();
            resolve();
            return;
        }

        try {
            const cachedAudio = AppState.ttsAudioCache.get(text);

            if (cachedAudio) {
                processAudioData(cachedAudio);
            } else if (AppState.ttsFailedTexts.has(text)) {
                fallbackMouthAnimation();
                resolve();
            } else {
                fetchTTSAudio(text).then(blob => {
                    AppState.ttsAudioCache.set(text, blob);
                    processAudioData(blob);
                }).catch(error => {
                    console.warn(`获取TTS音频失败: ${error.message}`);
                    AppState.ttsFailedTexts.add(text);
                    fallbackMouthAnimation();
                    resolve();
                });
            }
            
            // 处理音频数据的辅助函数
            function processAudioData(blob) {
                // 检查获取的blob是否有效
                if (!blob || blob.size === 0) {
                    throw new Error('获取到的音频数据为空');
                }
                
                // 保存当前播放的 Blob URL（克隆后需要重新使用）
                const audioUrl = URL.createObjectURL(blob);
                
                // 完全重置音频元素
                resetAudioElement(DOM.voicePlayer, audioUrl);
                
                // 设置音频源
                DOM.voicePlayer.src = audioUrl;
                
                // 存储当前播放的音频URL
                AppState.activeAudioUrl = audioUrl;
                AppState.currentPlayingAudioUrl = audioUrl;
                
                // 连接音频分析器
                if (!connectAudioAnalyser()) {
                    console.warn('音频分析器连接失败，将使用模拟口型动画');
                }
                
                // 预加载音频
                DOM.voicePlayer.load();
                
                // 播放结束后清理（不释放Blob URL，因为可能被缓存重复使用）
                DOM.voicePlayer.onended = function() {
                    setTimeout(() => {
                        resetVoiceState(false); // 不释放资源
                        resolve(); // 播放完成后解析Promise
                    }, 100);
                };
                
                // 错误处理
                DOM.voicePlayer.onerror = function(error) {
                    console.error('音频播放错误:', error);
                    resetVoiceState(false); // 不释放资源
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
        
        const blob = await response.blob();
        console.log(`获取TTS音频: ${text.substring(0, 20)}..., 大小: ${blob.size} bytes, 类型: ${blob.type}`);
        return blob;
        
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
function resetAudioElement(audioElement, audioUrl) {
    try {
        // 暂停播放
        audioElement.pause();
        
        // 重置时间
        audioElement.currentTime = 0;
        
        // 断开之前的音频源连接
        if (AppState.audioSource) {
            try {
                AppState.audioSource.disconnect();
            } catch (e) {}
            AppState.audioSource = null;
        }
        
        // 克隆节点以移除所有事件监听器和之前的连接
        const newAudioElement = audioElement.cloneNode(false);
        const parent = audioElement.parentNode;
        if (parent) {
            parent.replaceChild(newAudioElement, audioElement);
            DOM.voicePlayer = newAudioElement;
        }
        
        // 重新设置 src
        if (audioUrl) {
            DOM.voicePlayer.src = audioUrl;
        }
        
        console.log('音频元素已成功重置');
    } catch (e) {
        console.warn('重置音频元素时出错:', e);
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
            return false;
        }
        
        if (AppState.audioContext.state === 'suspended') {
            AppState.audioContext.resume();
        }
        
        if (AppState.audioSource) {
            try { AppState.audioSource.disconnect(); } catch (e) {}
            AppState.audioSource = null;
        }
        
        try {
            AppState.audioSource = AppState.audioContext.createMediaElementSource(DOM.voicePlayer);
        } catch (e) {
            resetAudioElement(DOM.voicePlayer);
            if (AppState.audioContext) {
                try { AppState.audioContext.close(); } catch (err) {}
            }
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            AppState.audioContext = new AudioContext();
            AppState.analyser = AppState.audioContext.createAnalyser();
            AppState.analyser.fftSize = 256;
            AppState.analyser.smoothingTimeConstant = 0.3;
            AppState.audioSource = AppState.audioContext.createMediaElementSource(DOM.voicePlayer);
        }
        
        AppState.audioSource.connect(AppState.analyser);
        AppState.analyser.connect(AppState.audioContext.destination);
        return true;
    } catch (error) {
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

function resetVoiceState(releaseResources = false) {
    if (DOM.voicePlayer) {
        DOM.voicePlayer.pause();
        DOM.voicePlayer.currentTime = 0;
    }
    
    AppState.isVoicePlaying = false;
    
    if (AppState.animationFrameId) {
        cancelAnimationFrame(AppState.animationFrameId);
        AppState.animationFrameId = null;
    }
    
    updateModelMouthShape(0);
    
    if (AppState.audioSource) {
        try { AppState.audioSource.disconnect(); } catch (e) {}
        AppState.audioSource = null;
    }
    
    if (releaseResources && AppState.activeAudioUrl) {
        setTimeout(() => {
            try { URL.revokeObjectURL(AppState.activeAudioUrl); } catch (e) {}
            AppState.activeAudioUrl = null;
            AppState.currentPlayingAudioUrl = null;
        }, 500);
    }
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
        
        const textContent = currentItem.text ? currentItem.text.trim() : '';

        if (textContent) {
            if (!AppState.ttsAudioCache.has(textContent) && !AppState.ttsFailedTexts.has(textContent)) {
                AppState.isWaitingForAudio = true;
                DOM.dialogue.textContent = '思考中……';
                while (!AppState.ttsAudioCache.has(textContent) && !AppState.ttsFailedTexts.has(textContent) && AppState.isProcessingSequence) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                }
                AppState.isWaitingForAudio = false;
                if (!AppState.isProcessingSequence) return;
            }

            if (!AppState.isProcessingSequence) return;

            AppState.currentSequenceIndex++;
            prepareNextAudio(AppState.currentSequenceIndex);

            const typewriterPromise = typewriterEffect(DOM.dialogue, textContent + ' ', false, 50, currentItem.emotion);
            const voicePromise = playVoice(textContent);
            await Promise.all([typewriterPromise, voicePromise]);
        } else if (currentItem.emotion) {
            applyExpression(currentItem.emotion);
            await new Promise(resolve => setTimeout(resolve, 300));
        }

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

document.addEventListener('DOMContentLoaded', initApp);
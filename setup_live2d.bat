@echo off

REM 切换到Live2D目录
cd live2d

REM 执行构建命令
echo 正在构建Live2D资源...
npm run build
if %errorlevel% neq 0 (
echo Live2D构建失败，请查看错误信息
pause
exit /b 1
)

echo Live2D资源构建成功

REM 返回到主目录
cd ..

echo Live2D模块设置完成，请运行app_with_live2d.py启动应用
pause
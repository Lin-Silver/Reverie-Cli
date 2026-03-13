@echo off
chcp 65001 >nul
".venv\Scripts\python.exe" generate_image.py --model models\t2i\bluePencilXL_v700.safetensors --prompt "{lolicon}{in a bathing suit}{Silver long hair}{got medium boobs}{Double Buns}{With a flower on her head}{cute buttocks}{white silk}" --output output\sample.png --steps 20 --seed %RANDOM%
pause
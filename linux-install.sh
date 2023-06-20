#!/bin/bash

# Используем цвета для логов
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

set -e

echo -e "${GREEN}Обновление пакетов...${NC}"
sudo apt update -y && sudo apt upgrade -y

echo -e "${GREEN}Установка русского языкового пакета...${NC}"
sudo apt install -y language-pack-ru

echo -e "${GREEN}Обновление локалей...${NC}"
sudo update-locale LANG=ru_RU.utf-8

echo -e "${GREEN}Установка software-properties-common...${NC}"
sudo apt install -y software-properties-common

echo -e "${GREEN}Добавление репозитория deadsnakes/ppa...${NC}"
sudo add-apt-repository -y ppa:deadsnakes/ppa

echo -e "${GREEN}Установка Python 3.11 и зависимостей...${NC}"
sudo apt install -y python3.11 python3.11-dev python3.11-gdbm python3.11-venv python3-pip

echo -e "${GREEN}Установка git...${NC}"
sudo apt install -y git

echo -e "${GREEN}Переход в домашнюю директорию...${NC}"
cd ~

sudo rm -rf FunPayVertex

echo -e "${GREEN}Клонирование репозитория FunPayVertex...${NC}"
git clone https://github.com/NightStrang6r/FunPayVertex

echo -e "${GREEN}Переход в директорию проекта...${NC}"
cd FunPayVertex

echo -e "${GREEN}Установка зависимостей бота...${NC}"
python3.11 setup.py

echo -e "${GREEN}Сейчас необходимо выполнить первичную установку${NC}"
python3.11 main.py

echo -e "${GREEN}Ок, теперь добавим бота как фоновый процесс${NC}"

echo -e "${GREEN}Установка curl...${NC}"
sudo apt-get install -y curl

echo -e "${GREEN}Загрузка NodeJS...${NC}"
curl -sL https://deb.nodesource.com/setup_16.x | sudo bash -

echo -e "${GREEN}Установка NodeJS...${NC}"
sudo apt -y install nodejs

echo -e "${GREEN}Установка pm2...${NC}"
sudo npm install -g pm2

pm2 start main.py --interpreter=python3.11 --name=FunPayVertex
pm2 save
pm2 startup

echo -e "${GREEN}Установка FunPayVertex завершена!${NC}"
echo -e "${GREEN}Для просмотра логов используйте команду: pm2 logs FunPayVertex${NC}"

pm2 logs FunPayVertex
# lab6_any_os_hard

# FUSE (Filesystem in userspace)

> 
> 
> 
> [FUSE](https://www.kernel.org/doc/html/next/filesystems/fuse.html#what-is-fuse)
> 
> С его помощью можно, например, примонтировать [Google Drive](https://github.com/astrada/google-drive-ocamlfuse) или [S3](https://github.com/s3fs-fuse/s3fs-fuse) (или много чего [еще](https://github.com/topics/fuse)) и обращаться к файлам в облаке так, как если бы они хранились на вашей локальной машине.
> 
> Простейший пример FUSE вы можете посмотреть в репозитории [libfuse](https://github.com/libfuse/libfuse/blob/master/example/passthrough.c). В этом примере корень текущей ФС монтируется в директорию. Все операции происходящие внутри этой директории passthrough пропускает через себя никак не изменяя их и вызывая стандартные функции libc.
> 
> Попробуйте скомпилировать passthrough командой
> 
> fuse3 --cflags --libs` -o passthrough , примонтировать его в любую директорию и посмотреть как он работает.
> 
> Вам предстоит написать собственную имплементацию FUSE выполняющую **одно** из предложенных заданий.
> 

# Выполнение лабораторной сводится с следующим шагам:

1. Выбор языка. Можно выбрать любой, практически у всех популярных ЯП есть свои библиотеки для работы с FUSE. Я рекомендую вам попробовать что-то низкоуровневое (C/C++, Rust)
2. Настройка инструментов

> Установите на вашу виртуалку пакеты fuse и libfuse-dev Подключите IDE к виртуалке, так будет гораздо легче писать код
> 
> 
> [VScode](https://code.visualstudio.com/docs/remote/ssh) [JetBrains](https://www.jetbrains.com/help/pycharm/remote-development-starting-page.html)
> 
> Также можно воспользоваться [SSHFS](https://github.com/libfuse/sshfs) (для MacOS и Linux) или [sshfs-win](https://github.com/winfsp/sshfs-win) (для Windows) для монтирования директорий из ВМ
> 
> Или же создать и примонтировать общую папку через VirtualBox
> 
> Полезная [ссылочка для работы с FUSE в докере](https://stackoverflow.com/questions/48402218/fuse-inside-docker) и [просмотра файлов внутри докера](https://stackoverflow.com/questions/52856353/docker-accessing-files-inside-container-from-host)
> 
1. Написание кода. Вам нужно будет переопределить логику работы операций (read, write, mkdir, readlink и т.д.). Решите в каких операциях вы будете менять логику, какие операции оставите без изменений и будете вызывать их версии из стандартных библиотек, а какие и вовсе уберете оставив в виде noop.
2. Тестирование. В конце не забудьте убедиться что выполнение команд ls, cat, rm, rmdir, ln, chown, cd, echo 1 > file не приводят к крашу ФС.

# Задания

## Хранилище файлов в Discord/Telegram

> Нужно реализовать подключение по API к Discord или Telegram для сохранения файлов в каналах.
> 
> 
> Запись файла должна представлять из себя создание нового сообщения с файлом в канале. Если файл уже существует, то нужно сначала создать новое сообщение и только после его успешного создания удалить старое.
> 
> Директории
> 
> В Telegram при перемещении файла в директорию к сообщению нужно добавлять тег с названием директории. При листинге директории нужно отдавать список файлов с тегом. Удаление директории должно приводить к удалению всех файлов с соответствующим тегом.
> 
> Для Discord запись файлов в корневую директорию должна сохранять файлы в основной текстовый канал. При создании директории должен создаваться новый канал и файлы записанные в новую директорию должны загружаться в этот канал. При листинге директории нужно отдавать список файлов из канала. При удалении директории канал должен удаляться.
> 
> Создание вложенных директорий реализовывать не нужно
> 
> Запрос ctime и mtime должен возвращать дату создания сообщения с файлом
> 
> Остальные операции (смена владельца файла, создание ссылок) можно не реализовывать
> 
> Для хранения мета информации можно как использовать локальный файл, так и специальное сообщение в канале
> 

## Конвертация файлов на лету

> В вашу программу будет передаваться путь до директории с картинками в png формате, оттуда она будет получать изначальные файлы.
> 
> 
> При листинге директории ваша программа должна отдавать список оригинальных файлов и (если применимо) их сконвертированные копии. Пример:
> 
> При попытке открыть файл jpg оригинальный png должен конвертироваться и возвращаться в jpg формате. Для того чтобы убедиться что файл действительно сконвертировался можно воспользоваться утилитой file
> 
> Все остальные операции должны переноситься на оригинальную директорию. Например mkdir mounted_dir/new_dir создаст директорию в original_dir.
> 
> При желании с преподавателем можно обсудить другие форматы для конвертации, например flac-
> 
> >mp3 или md->pdf
> 

## Группировка mp3 файлов

> У mp3 файлов есть теги содержащие разную мета информации об аудиофайле, например имя исполнителя, год записи песни, жанр и т.д. Ваша программа будет получать путь до директории с mp3 файлами и должна будет пройдясь рекурсивно по всем поддиректориям составить 3 директории в которых будут сгруппированы файлы согласно тегам: Artist, Year и Genre.
> 
> 
> Пример:
> 
> ФС должна быть read only
> 
> Обратите внимание что у некоторых файлов может быть несколько жанров
> 
> При попытке прочитать файл из примонтированной директории должен отдаваться оригинальный файл
> 

## Авторазархивирование

> В вашу программу будет передаваться путь до директории с разными файлами, в том числе архивами. Для каждого архива в примонтированной ФС вам необходимо показывать директорию с содержимым архива и возможностью прочитать содержимое файлов.
> 
> 
> Пример поведения ФС:
> 
> Архивные директории (archive, labs) должны быть read only
> 
> Все остальные операции должны переноситься на оригинальную директорию. Например mkdir mounted_dir/new_dir создаст директорию в original_dir
> 
> Ваша имплементация должна поддерживать минимум 2 архивных формата на ваш выбор
> 

## ФС с кастомными правилами

> Ваша задача реализовать ФС которая будет в зависимости от конфига и типа файла исполнять разные операции.
> 
> 
> Пример формата конфига:
> 

[Untitled Database](lab6_any_os_hard%20(1)%20d349bf3965cd40d4aa382b4369429686/Untitled%20Database%20321e6821dcc0442e9ddda727c9387e0e.csv)

> Формат вашего конфига не обязательно должен быть в yaml формате и не обязательно именно с такими названиеми полей. Но там должны быть:
> 
> 
> Массив с расширениями файлов
> 
> У перечисленных расширений должно быть поле read или write где описываются операции которые должны быть выполнены при чтении или записи файла с определенным расширением
> 
> Поля read/write могут быть строкой или массивом если планируется делать несколько операций с файлом
> 
> Переменные и выполнении команд
> 
> которые будут подставляться при
> 
> Специальное расширение other обозначающее все остальные расширения файлов кроме перечисленных
> 
> Специальная строка pass обозначающая операцию по умолчанию. В примере все файлы с расширениями не md или png будут открываться как обычно, а затем логироваться информация об этом
> 
> Поле DIRECTORY_LISTING где будут команды, исполняемые при листинге директории ( ) Пример:
> 

## Свое задание

> Если у вас есть другая идея с использованием FUSE и вы хотите реализовать ее, то обсудите это с преподавателем чтобы расписать ТЗ к вашему заданию.
> 

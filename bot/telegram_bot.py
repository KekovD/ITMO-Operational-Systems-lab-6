import os
import shutil
import threading
import re

from telegram import Update, MessageEntity, Bot
from telegram.ext import CallbackContext, ConversationHandler

from bot.converter import create_empty_jpg
from bot.collect_metadata import save_metadata_to_storage
from config import logger, MOUNT_POINT, TOKEN, STORAGE_PATH, BACKUP_FILE
from fs_utils import unmount_fs, start_fuse

fuse_stopped = False


def check_fuse(update):
    if fuse_stopped:
        update.message.reply_text('Файловая система не активна.')
        return ConversationHandler.END


def split_and_send_message(update: Update, message: str):
    max_message_length = 4096
    for i in range(0, len(message), max_message_length):
        update.message.reply_text(message[i:i + max_message_length], parse_mode='Markdown')


def check_mention(update, context) -> bool:
    if 'bot_username' not in context.user_data:
        context.user_data['bot_username'] = "@" + Bot(TOKEN).get_me().username

    bot_username = context.user_data['bot_username']
    entities = update.message.parse_entities([MessageEntity.MENTION]).values()

    return bot_username in entities


def handle_private(update, context):
    message_text = update.message.text

    if message_text.startswith('/stop'):
        stop_command(update, context)

    elif message_text.startswith('/start'):
        start_command(update, context)

    elif message_text.startswith('/mkdir'):
        mkdir(update, context)

    elif message_text.startswith('/mv'):
        move(update, context)

    elif message_text.startswith('/ls'):
        list_files(update, context)

    elif message_text.startswith('/trls'):
        tree_list_files(update, context)

    elif message_text.startswith('/rm'):
        remove(update, context)

    elif message_text.startswith('/cp'):
        cp(update, context)

    elif message_text.startswith('/get'):
        get_document(update, context)

    elif message_text.startswith('/convert '):
        match = re.search(r'/convert (\S+)', message_text)

        if match:
            path = match.group(1)
            if os.path.exists(path):
                convert_command(update, context, path)
            else:
                update.message.reply_text('Путь не существует. Пожалуйста, введите действительный путь.')


def handle_mention(update, context):
    if check_mention(update, context):
        message_text = update.message.text
        words = message_text.split()

        if len(words) > 1:
            command = words[1]

            if command == '/start':
                start_command(update, context)

            elif command == '/stop':
                stop_command(update, context)

            elif command == '/mkdir':
                mkdir(update, context)

            elif command == '/mv':
                move(update, context)

            elif command == '/ls':
                list_files(update, context)

            elif command == '/trls':
                tree_list_files(update, context)

            elif command == '/rm':
                remove(update, context)

            elif command == '/cp':
                cp(update, context)

            elif command == '/get':
                get_document(update, context)

            elif command == '/convert':
                if len(words) > 2:
                    path = words[2]

                    if os.path.exists(path):
                        convert_command(update, context, path)
                    else:
                        update.message.reply_text('Путь не существует. Пожалуйста, введите действительный путь.')
                else:
                    update.message.reply_text('Пожалуйста, укажите путь для команды /convert.')


def cancel(update, context):
    update.message.reply_text('Операция отменена.')
    return ConversationHandler.END


def save_file_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'^/save(?:\s+"([^"]+)"|\s+(\S+))?$', message_text)
    if not match:
        update.message.reply_text('Неверный формат команды. Используйте /save или /save "<directory>"')
        return ConversationHandler.END

    directory = match.group(1) or match.group(2)
    if directory:
        if directory.startswith('/'):
            update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
            return ConversationHandler.END
        context.user_data['save_dir'] = directory
    else:
        context.user_data['save_dir'] = MOUNT_POINT

    update.message.reply_text('Отправьте файл или введите /cancel_save для отмены.')
    context.user_data['save_user_id'] = update.message.from_user.id
    context.user_data['save_context'] = 'waiting_for_file_private'
    context.user_data['attempt_count'] = 0
    return 'waiting_for_file_private'


def save_file_mention_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if check_mention(update, context):
        bot_username = context.bot.username
        message_text = update.message.text
        pattern = fr'^@{bot_username}\s+/save(?:\s+"([^"]+)"|\s+(\S+))?$'
        match = re.search(pattern, message_text)
        if not match:
            update.message.reply_text(f'Неверный формат команды. Используйте /save или /save "<directory>"')
            return ConversationHandler.END

        directory = match.group(1) or match.group(2)
        if directory:
            if directory.startswith('/'):
                update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
                return ConversationHandler.END
            context.user_data['save_dir'] = directory
        else:
            context.user_data['save_dir'] = MOUNT_POINT

        update.message.reply_text(f'Отправьте файл или введите /cancel_save@{bot_username} для отмены.')
        context.user_data['save_user_id'] = update.message.from_user.id
        context.user_data['save_context'] = 'waiting_for_file_mention'
        context.user_data['attempt_count'] = 0
        return 'waiting_for_file_mention'


def save_file(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    if 'save_user_id' in context.user_data and context.user_data['save_user_id'] == update.message.from_user.id:
        file_info = None
        filename = None

        if update.message.document:
            file_info = update.message.document
            filename = file_info.file_name
        elif update.message.photo:
            file_info = update.message.photo[-1]
            filename = f"photo_{file_info.file_unique_id}.jpg"
        elif update.message.video:
            file_info = update.message.video
            filename = file_info.file_name
        elif update.message.animation:
            file_info = update.message.animation
            filename = file_info.file_name
        elif update.message.audio:
            file_info = update.message.audio
            filename = file_info.file_name

        if file_info:
            file_id = file_info.file_id
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(f"Received file from chat_id: {chat_id}")
            logger.info(f"Received file from user_id: {user_id}")
            logger.info(f"File received: file_id={file_id}, filename={filename}")

            save_dir = context.user_data.get('save_dir', MOUNT_POINT)
            local_path = os.path.join(MOUNT_POINT, save_dir, filename)

            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            if os.path.exists(local_path):
                update.message.reply_text(
                    f"Файл с именем {filename} уже существует. Пожалуйста, отправьте файл с другим именем.")
                return context.user_data['save_context']

            file = context.bot.get_file(file_id)
            file.download(local_path)
            logger.info(f"File downloaded to: {local_path}")

            update.message.reply_text(f"Файл {filename} загружен и сохранен на вашем сервере.")
            save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
            return ConversationHandler.END
        else:
            context.user_data['attempt_count'] += 1
            if context.user_data['attempt_count'] >= 3:
                update.message.reply_text("Превышено количество попыток отправки файла.")
                return ConversationHandler.END
            else:
                if context.user_data['save_context'] == 'waiting_for_file_mention':
                    bot_username = context.user_data['bot_username']
                    update.message.reply_text(f'Отправьте файл или введите /cancel_save{bot_username} для отмены.')
                else:
                    update.message.reply_text('Отправьте файл или введите /cancel_save для отмены.')
                return context.user_data['save_context']
    else:
        return context.user_data['save_context']


def get_document(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    match = re.search(r'/get\s+(?:"([^"]+)"|(\S+))', message_text)
    if not match:
        update.message.reply_text("Ошибка: используйте /get <filename>.")
        return

    relative_path = match.group(1) or match.group(2)
    if relative_path is None:
        update.message.reply_text("Ошибка: используйте /get <filename>.")
        return

    absolute_path = os.path.join(MOUNT_POINT, relative_path)

    if not os.path.exists(absolute_path) or not os.path.isfile(absolute_path):
        update.message.reply_text(f"Ошибка: файл {relative_path} не найден.")
        return

    with open(absolute_path, 'rb') as file:
        update.message.reply_document(document=file)


def mkdir(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/mkdir\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, message_text)
    if not match:
        pattern = r'/mkdir\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, message_text)

    if match:
        directory_name = match.group(1) or match.group(2)

        if re.search(r'/mkdir\s+(\S+)\s+(\S+)', update.message.text) and re.search(r'/mkdir\s+"([^"]+)"',
                                                                                   message_text) is None:
            update.message.reply_text("Ошибка: команда должна содержать только одно слово.")
            return ConversationHandler.END

        if directory_name.startswith('/'):
            update.message.reply_text("Ошибка: имя директории не должно начинаться с `/`.")
            return ConversationHandler.END

        new_dir_path = os.path.join(MOUNT_POINT, directory_name)

        if os.path.exists(new_dir_path):
            update.message.reply_text(f"Ошибка: директория {directory_name} уже существует.")
            return ConversationHandler.END

        try:
            os.makedirs(new_dir_path, exist_ok=True, mode=0o777)
            update.message.reply_text(f"Директория {directory_name} успешно создана.")
            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(
                f"Directory {directory_name} created successfully at {new_dir_path} from chat_id {chat_id} and user_id {user_id}.")
            save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Ошибка при создании директории {directory_name}: {e}")
            update.message.reply_text(f"Ошибка при создании директории.")
    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь имя директории. Убедитесь, что команда введена правильно.")

    return ConversationHandler.END


def move(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    message_text = update.message.text
    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/mv\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, message_text)
    if not match:
        pattern = r'/mv\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, message_text)

    if match:
        source = match.group(1) or match.group(2)
        destination = match.group(3) or match.group(4)

        source_path = os.path.join(MOUNT_POINT, source.lstrip('/'))
        destination_path = os.path.join(MOUNT_POINT, destination.lstrip('/'))

        if source_path == destination_path:
            update.message.reply_text(f"Ошибка: Исходный путь {source} и путь назначения {destination} равны.")
            return ConversationHandler.END

        if not os.path.exists(source_path):
            update.message.reply_text(f"Ошибка: Исходный путь {source} не существует.")
            return ConversationHandler.END

        if not os.path.exists(destination_path):
            update.message.reply_text(f"Ошибка: Путь назначения {destination} не существует.")
            return ConversationHandler.END

        try:
            shutil.move(source_path, destination_path)
            update.message.reply_text(f"{source} успешно перемещен(а) в {destination}.")

            chat_id = update.message.chat_id
            user_id = update.message.from_user.id
            logger.info(f"{source} перемещен(а) в {destination} от chat_id {chat_id} и user_id {user_id}.")
            save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
        except Exception as e:
            logger.error(f"Ошибка при перемещении {source} в {destination}: {e}")
            update.message.reply_text(f"Ошибка при перемещении")
    else:
        update.message.reply_text("Ошибка: неправильный формат команды. Используйте /mv <источник> <назначение>.")

    return ConversationHandler.END


def copy_path_with_suffix(src, dst):
    if os.path.exists(dst) and os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    original_dst = dst
    counter = 1
    while os.path.exists(dst):
        dst = add_suffix(original_dst, counter, os.path.isdir(src))
        counter += 1
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy(src, dst)

    return dst


def add_suffix(path, counter, is_dir):
    dirname, basename = os.path.split(path)
    if is_dir:
        new_basename = f"{basename}({counter})"
    else:
        name, ext = os.path.splitext(basename)
        new_basename = f"{name}({counter}){ext}"
    return os.path.join(dirname, new_basename)


def cp(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    bot_username = context.bot.username
    pattern = fr'@{bot_username}\s+/cp\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
    match = re.search(pattern, update.message.text)
    if not match:
        pattern = r'/cp\s+(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(\S+))'
        match = re.search(pattern, update.message.text)

    if match:
        src = match.group(1) or match.group(2)
        dst = match.group(3) or match.group(4)

        if src and dst:
            src = src.lstrip('/')
            dst = dst.lstrip('/')

            src_path = os.path.join(MOUNT_POINT, src)
            dst_path = os.path.join(MOUNT_POINT, dst)

            if not os.path.exists(src_path):
                update.message.reply_text(f"Ошибка: исходный путь {src} не существует.")
                return ConversationHandler.END

            try:
                new_dst_path = copy_path_with_suffix(src_path, dst_path)
                relative_new_dst_path = os.path.relpath(new_dst_path, MOUNT_POINT)
                update.message.reply_text(f"{src} успешно скопирован в {relative_new_dst_path}.")
                chat_id = update.message.chat_id
                user_id = update.message.from_user.id
                logger.info(
                    f"Path {src} copied to {relative_new_dst_path} from chat_id {chat_id} and user_id {user_id}.")
                save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
            except Exception as e:
                logger.error(f"Error copying {src} to {dst}: {e}")
                update.message.reply_text(f"Ошибка при копировании {src} в {dst}.")
        else:
            update.message.reply_text("Ошибка: используйте /cp <src> <dst>.")
    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь пути. Убедитесь, что команда введена правильно в формате /cp \"<src>\" \"<dst>\" или /cp <src> <dst>."
        )

    return ConversationHandler.END


def file_list() -> list[str]:
    files_list = []

    for root, dirs, files in os.walk(MOUNT_POINT):
        for file in files:
            relative_path = os.path.relpath(root, MOUNT_POINT)

            if relative_path == '.':
                relative_path = '/'
            else:
                relative_path = f"/{relative_path}"

            files_list.append(f"<{relative_path}> {file}")
    return files_list


def tree(directory: str, prefix: str = '') -> str:
    result = []
    contents = os.listdir(directory)
    contents = sorted(contents, key=lambda s: s.lower())
    pointers = ['├── '] * (len(contents) - 1) + ['└── ']

    for pointer, path in zip(pointers, contents):
        full_path = os.path.join(directory, path)
        if os.path.isdir(full_path):
            result.append(f"{prefix}{pointer}{path}/")
            if pointer == '└── ':
                extension = '    '
            else:
                extension = '│   '
            result.append(tree(full_path, prefix=prefix + extension))
        else:
            result.append(f"{prefix}{pointer}{path}")
    return '\n'.join(result)


def list_path_check(update, directory_path):
    if '/' != directory_path[0]:
        update.message.reply_text("Ошибка: имя директории должно начинаться с `/`.")
        return ConversationHandler.END

    check_dir_path = os.path.join(MOUNT_POINT, directory_path[1:])

    if not os.path.exists(check_dir_path):
        update.message.reply_text(f"Ошибка: директории {directory_path} не существует")
        return ConversationHandler.END


def list_files(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    directory_path = '/'
    match = re.search(r'/ls\s+(?:"([^"]+)"|(\S+))', update.message.text)

    if match:
        directory_path = match.group(1) or match.group(2)
        if directory_path is None:
            update.message.reply_text("Ошибка: используйте /ls или /ls <dir>.")
            return ConversationHandler.END

        if list_path_check(update, directory_path) is ConversationHandler.END:
            return ConversationHandler.END

    files_list = file_list()

    filtered_files = [file for file in files_list if file.startswith(f"<{directory_path}")]

    if files_list:
        files_output = f"```\n{'\n'.join(filtered_files)}```"
        message = files_output
    else:
        message = f"Директория {filtered_files} и все поддиректории пусты."

    split_and_send_message(update, message)
    return ConversationHandler.END


def tree_list_files(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    directory_path = '/'
    match = re.search(r'/trls\s+(?:"([^"]+)"|(\S+))', update.message.text)

    if match:
        directory_path = match.group(1) or match.group(2)
        if directory_path is None:
            update.message.reply_text("Ошибка: используйте /trls или /trls <dir>.")
            return ConversationHandler.END

        if list_path_check(update, directory_path) is ConversationHandler.END:
            return ConversationHandler.END

    files_list = file_list()
    filtered_files = [file for file in files_list if file.startswith(f"<{directory_path}")]

    if filtered_files:
        tree_output = tree(os.path.join(MOUNT_POINT, directory_path.strip('/')))
        tree_lines = [line for line in tree_output.split('\n') if line.strip()]
        message = f"```\n{'\n'.join(tree_lines)}\n```"
    else:
        message = f"Директория {directory_path} и все поддиректории пусты."

    split_and_send_message(update, message)
    return ConversationHandler.END


def remove_file(update, context, target_path):
    if target_path.startswith('/'):
        update.message.reply_text("Ошибка: путь не должен начинаться с `/`.")
        return ConversationHandler.END

    full_path = os.path.join(MOUNT_POINT, target_path)

    if not os.path.exists(full_path):
        update.message.reply_text(f"Ошибка: путь {target_path} не существует.")
        return ConversationHandler.END

    try:
        if os.path.isdir(full_path):
            logger.info("in dir")
            shutil.rmtree(full_path)
        else:
            logger.info("in file")
            os.remove(full_path)
        update.message.reply_text(f"{target_path} успешно удален(а).")
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id
        logger.info(f"{target_path} удален(а) от chat_id {chat_id} и user_id {user_id}.")
        save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    except Exception as e:
        logger.error(f"Ошибка при удалении {target_path}: {e}")
        update.message.reply_text(f"Ошибка при удалении {target_path}.")


def remove(update, context):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    match = re.search(r'/rm\s+"([^"]+)"', update.message.text)
    if match:
        target_path = match.group(1)

        if re.search(r'/rm\s+"([^"]+)"\s+"([^"]+)"', update.message.text) is not None:
            update.message.reply_text("Ошибка: команда должна содержать только один аргумент.")
            return ConversationHandler.END

        remove_file(update, context, target_path)

    elif re.search(r'/rm\s+(\S+)', update.message.text):
        match = re.search(r'/rm\s+(\S+)', update.message.text)

        target_path = match.group(1)

        if re.search(r'/rm\s+(\S+)\s+(\S+)', update.message.text) is not None:
            update.message.reply_text("Ошибка: команда должна содержать только один аргумент.")
            return ConversationHandler.END

        remove_file(update, context, target_path)

    else:
        update.message.reply_text(
            "Ошибка: не удалось извлечь путь. Убедитесь, что команда введена правильно и путь заключен в кавычки.")

    return ConversationHandler.END


def start_command(update: Update, context: CallbackContext):
    global fuse_stopped

    fuse_thread = threading.Thread(target=start_fuse)
    fuse_thread.start()

    fuse_stopped = False

    update.message.reply_text('Готов принимать команды для работы с файловой системой.')
    save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    return ConversationHandler.END


def stop_command(update: Update, context: CallbackContext):
    if check_fuse(update) is ConversationHandler.END:
        return ConversationHandler.END

    global fuse_stopped

    user_id = update.message.from_user.id
    logger.info(f"Stop command received from user_id: {user_id}")

    update.message.reply_text('Останавливаю работу файловой системы...')

    unmount_fs()
    fuse_stopped = True

    logger.info("Fuse stopped")
    save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)
    return ConversationHandler.END


def convert_command(update: Update, context: CallbackContext, path):
    try:
        converted_files = []

        for filename in os.listdir(path):
            if filename.endswith(".png"):
                png_path = os.path.join(path, filename)
                output_path_jpg = os.path.join(MOUNT_POINT, filename[:-3] + 'jpg')
                output_path_png = os.path.join(MOUNT_POINT, filename)
                create_empty_jpg(output_path_jpg)
                shutil.copy(png_path, output_path_png)
                converted_files.append(f"{filename} -> {filename[:-3]}jpg")

        converted_files_message = "\n".join(converted_files)

        update.message.reply_text(f"Файлы в директории {path} успешно обработаны:\n{converted_files_message}")
        chat_id = update.message.chat_id
        user_id = update.message.from_user.id

        save_metadata_to_storage(MOUNT_POINT, STORAGE_PATH, BACKUP_FILE)

        logger.info(
            f"Files in directory {path} processed successfully from chat_id {chat_id} and user_id {user_id}.")
    except Exception as e:
        logger.error(f"Error processing files in directory {path}: {e}")
        update.message.reply_text(f"Ошибка при обработке файлов в директории: {e}")

    return ConversationHandler.END

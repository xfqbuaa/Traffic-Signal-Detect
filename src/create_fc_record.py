#coding:UTF-8
import os
import hashlib
import io
import random
import shutil
import configparser
import pylab as plt
import tensorflow as tf

from tqdm import tqdm
from lxml import etree
from PIL import Image, ImageDraw, ImageFont
from object_detection.utils import dataset_util
from object_detection.utils import label_map_util

 

def create_tf_record(examples_list, output_filename):
    
    writer = tf.python_io.TFRecordWriter(output_filename)
    for tf_example in examples_list:
        writer.write(tf_example[0].SerializeToString())

def save_img_with_box(image, target_list, img_name, group):

    for target in target_list:
        x1, y1, x2, y2, label = target
        box = (x1, y1), (x2, y2)
        font = ImageFont.truetype(cf.get('font_path', 'simsun'), 20)
        drawObject = ImageDraw.Draw(image)  
        drawObject.rectangle(box, outline = "red")  
        drawObject.text([x1+50, y1+50], label,"red", font=font)

    save_dir = os.path.join(image_vis_path, group)
    if not os.path.exists(save_dir):
        os.makedirs(save_dir) 
    image.save(os.path.join(save_dir, img_name))
    # plt.imshow(image) 
    # plt.show()
    # exit(0) 

def process_sigle_object(data, i, frame_number, img_name, label_map_dict,
                        xmin, ymin, xmax, ymax, classes, classes_text, width, height):
    target_order = ('00000' + str(i))[-5:]
    target_name = 'Frame' + str(frame_number) + 'Target' + target_order
    # postion: x,y,width,height
    try:
        position_list = data[target_name]['Position'].split()
    except KeyError:
        # 有的数据里number是3个，但实际只有2个标注。 源数据异常只进行规避。
        # print("KeyError. data: " + ' target_name: ' + target_name + ' img_path" ' + img_path)
        target_num_not_match.append([img_name, target_name])
        return 1
    x1, y1, w, h = [ int(i) for i in position_list]
    x2 = x1 + w
    y2 = y1 + h

    # print(x1, y1, w, h)
    xmin.append(1.0*x1 / width)
    ymin.append(1.0*y1 / height)
    xmax.append(1.0*x2 / width)
    ymax.append(1.0*y2 / height)
    
    class_name = data[target_name]['Type'].strip('\"')
    classes_text.append(class_name.encode('utf8'))
    # print(label_map_dict, class_name, label_map_dict["警1-T型交叉右"])
    try:
        classes.append(label_map_dict[class_name])
    except KeyError:
        # print 'Class name not match: ', class_name
        if class_name not in class_not_match: class_not_match[class_name] = 0
        class_not_match[class_name] += 1
        return None 

    return [x1, y1, x2, y2, class_name] 

def dict_to_tf_example(data,
                       label_map_dict,
                       img_path,
                       img_name,
                       ignore_difficult_instances=False):
    """Convert XML derived dict to tf.Example proto.
    Notice that this function normalizes the bounding box coordinates provided
    by the raw data.
    """
    # 读取图片数据
    with tf.gfile.GFile(img_path, 'rb') as fid:
        encoded_jpg = fid.read()
    encoded_jpg_io = io.BytesIO(encoded_jpg)
    image = Image.open(encoded_jpg_io)
    # key = hashlib.sha256(encoded_jpg).hexdigest()

    width = cf.getint('image_shape', 'width')
    height = cf.getint('image_shape', 'height')

    xmin = []
    ymin = []
    xmax = []
    ymax = []
    classes = []
    classes_text = []

    # Get frame: TSD-Signal-00120-00001.png  --> 00001
  
    frame_number = img_name.split('-')[-1].replace('.png', '')
    group = img_name.split('-')[-2]

    assert 'Frame' + frame_number + 'TargetNumber' in data, 'KeyError: img_name: ' + img_name + ' Frame: ' + frame_number
    target_count = int(data['Frame' + frame_number + 'TargetNumber'])

    if target_count == 0:
        zero_object_img.append(img_name)
        return None
    target_list = []
    for i in range(target_count):
        ret = process_sigle_object(data, i, frame_number, img_name, label_map_dict,
                                xmin, ymin, xmax, ymax, classes, classes_text, width, height)
        if ret is None: return None
        if ret == 1: continue
        target_list.append(ret)

    if save_img:    
        save_img_with_box(image, target_list, img_name, group)

    # 把一张图片里的所有object都装到example
    example = tf.train.Example(features=tf.train.Features(feature={
      'image/height': dataset_util.int64_feature(height),
      'image/width': dataset_util.int64_feature(width),
      'image/filename': dataset_util.bytes_feature(img_name.encode('utf8')),
      'image/source_id': dataset_util.bytes_feature(img_name.encode('utf8')),
      # 'image/key/sha256': dataset_util.bytes_feature(key.encode('utf8')),
      'image/encoded': dataset_util.bytes_feature(encoded_jpg),
      'image/format': dataset_util.bytes_feature('png'.encode('utf8')),
      'image/object/bbox/xmin': dataset_util.float_list_feature(xmin),
      'image/object/bbox/xmax': dataset_util.float_list_feature(xmax),
      'image/object/bbox/ymin': dataset_util.float_list_feature(ymin),
      'image/object/bbox/ymax': dataset_util.float_list_feature(ymax),
      'image/object/class/text': dataset_util.bytes_list_feature(classes_text),
      'image/object/class/label': dataset_util.int64_list_feature(classes),
    }))
    return example

def get_label_dict(label_path):
    label_map_dict = {}
    with open(label_path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            if not line.split():
                continue
            line = line.strip()
            number, name = line.split(' ', 1)
            label_map_dict[name] = int(number)

    # assert len(label_map_dict) == 77
    return label_map_dict

def read_norm_data(img_data, label_map_dict):
    new_data_path = os.path.join(data_dir, 'TrafficNorm') 

    for img_dir in tqdm(os.listdir(new_data_path)):
        current_dir_path = os.path.join(new_data_path, img_dir)
        label_path = os.path.join(current_dir_path, 'labels.txt')
        if not os.path.isfile(label_path):
            print("label not exist:", label_path)
            continue
        with open(label_path) as f:
            lines = f.readlines()
            for i in range(len(lines)):
                line = lines[i].split()
                img_name, x1, y1, w, h = line
                x1, y1, w, h = int(x1), int(y1), int(w), int(h)
                x2, y2 = x1 + w, y1 + h
                img_path = os.path.join(current_dir_path, img_name)
                img_path_upper = os.path.join(current_dir_path, img_name.upper())

                if os.path.isfile(img_path):
                    path = img_path
                elif os.path.isfile(img_path_upper):
                    path = img_path_upper
                else:
                    continue   

                with tf.gfile.GFile(path, 'rb') as fid:
                    encoded_jpg = fid.read()
                encoded_jpg_io = io.BytesIO(encoded_jpg)
                image = Image.open(encoded_jpg_io)
                width = image.width
                height = image.height
                xmin = [1.0*x1 / width]
                ymin = [1.0*y1 / height]
                xmax = [1.0*x2 / width]
                ymax = [1.0*y2 / height]
                if x2 > width or y2 > height:
                    print(line, label_path)
                    exit(-1)
                class_name = img_dir
                classes_text = [class_name.encode('utf8')]
                classes = [label_map_dict[class_name]]
            
                example = tf.train.Example(features=tf.train.Features(feature={
                  'image/height': dataset_util.int64_feature(height),
                  'image/width': dataset_util.int64_feature(width),
                  'image/filename': dataset_util.bytes_feature(img_name.encode('utf8')),
                  'image/source_id': dataset_util.bytes_feature(img_name.encode('utf8')),
                  # 'image/key/sha256': dataset_util.bytes_feature(key.encode('utf8')),
                  'image/encoded': dataset_util.bytes_feature(encoded_jpg),
                  'image/format': dataset_util.bytes_feature('jpeg'.encode('utf8')),
                  'image/object/bbox/xmin': dataset_util.float_list_feature(xmin),
                  'image/object/bbox/xmax': dataset_util.float_list_feature(xmax),
                  'image/object/bbox/ymin': dataset_util.float_list_feature(ymin),
                  'image/object/bbox/ymax': dataset_util.float_list_feature(ymax),
                  'image/object/class/text': dataset_util.bytes_list_feature(classes_text),
                  'image/object/class/label': dataset_util.int64_list_feature(classes),
                }))
                img_data.append([example, path])
                if save_img:    
                    target_list = [[x1, y1, x2, y2, img_dir]]
                    save_img_with_box(image, target_list, img_name, img_dir)
    return img_data

def create_img_data_dict(images_dir, annotations_dir, label_map_path):
    # 获取TSD-Signal下每一组图片 signal000 - signal 120
    # 对每一组图片，打开对应的xml，获取每个图片的信息
    # 将图片-信息 存入到dict
    # shuffle后写入对应的record
    img_data = []
    
    print('Prossing Traffic Sign data...')
    # label_map_dict = label_map_util.get_label_map_dict(label_map_path)
    label_map_dict = get_label_dict(label_map_path)

    for group_name in tqdm(os.listdir(images_dir)):
        img_group_dir = os.path.join(images_dir, group_name)
        if not os.path.isdir(img_group_dir):
            continue

        xml_path = os.path.join(annotations_dir, group_name + '-GT.xml')
        # xml_path = '/home/cabbage/Desktop/FC2017/任务2-交通信号检测/data/TSD-Signal-GT/TSD-Signal-00120-GT.xml'
        with tf.gfile.FastGFile(xml_path, 'rb') as fid:
        # with open(xml_path, 'rt', encoding='latin-1') as fid:
            xml_str = fid.read()
            xml = etree.fromstring(xml_str)

            data = dataset_util.recursive_parse_xml_to_dict(xml)['opencv_storage']  
            frame_count = data['FrameNumber']
            for img_name in os.listdir(img_group_dir):
                frame_number = img_name.replace(group_name+'-', '').replace('.png', '')
                if not frame_number.isdigit():
                    print('Error: image name not match. ', img_name, frame_number)
                    continue 
                img_path = os.path.join(img_group_dir, img_name)
                tf_example = dict_to_tf_example(data, label_map_dict, img_path, img_name)
                if tf_example:
                    img_data.append([tf_example, img_path])
    
    if is_read_norm_data:
        print('Prossing TrafficNorm data...')
        img_data = read_norm_data(img_data, label_map_dict)

    return img_data

def main():
    '''
    imgs eg:    ./TSD-Signal/TSD-Signal-00120/TSD-Signal-00120-00000.png
    xmls eg:    ./TSD-Signal-GT/TSD-Signal-00120-GT.xml
    labels are at:  ./traffic.pbtxt
    xml: 
      <Frame00000Target00000>     # <Frame*Target***>
      <Type>警1-前方施工</Type>
      <Position>
    '''    
    images_dir = os.path.join(data_dir, 'TSD-Signal')
    annotations_dir = os.path.join(data_dir, 'TSD-Signal-GT') 
    label_map_path = os.path.join(data_dir, 'traffic.label')     # traffic.pbtxt 格式读取中文字符有问题

    # 读取image和xml文件，得到image-xml对应字典
    # img_data元素为[data, img_path] img_path用于复制图片到test_dir
    img_data = create_img_data_dict(images_dir, annotations_dir, label_map_path)
    examples_list = img_data
    assert len(examples_list) != 0, "Error: examples_list is empty."
   
    # 将图片随机分布，一部分用来训练,一部分用来验证
    random.seed(42)
    random.shuffle(examples_list)
    num_examples = len(examples_list)
    num_train = int(0.9 * num_examples)
    train_examples = examples_list[:num_train]
    val_examples = examples_list[num_train:]
    print("train numbers: ", num_examples, " val numbers: ", len(val_examples))

    print("Creating records files...")
    output_dir = os.path.join(data_dir, 'records')
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    train_output = os.path.join(output_dir, 'train.record')
    val_output = os.path.join(output_dir, 'val.record')
    create_tf_record(train_examples, train_output)
    create_tf_record(val_examples, val_output)

    print('Copy test images to test dir:')
    for example in tqdm(val_examples):
        img_path = example[1]
        # if 'TSD' in img_path:
        group = img_path.split('/')[-2]
        group_dir = os.path.join(test_img_dir, group)
        if not os.path.exists(group_dir):
            os.makedirs(group_dir) 
        shutil.copy(img_path, group_dir) 


save_img = False
is_read_norm_data = True
zero_object_img = []
class_not_match = {}
target_num_not_match = []
data_dir = '../data'
test_img_dir = os.path.join(data_dir, 'test_samples')
image_vis_path = os.path.join(data_dir, 'input_img_vis_test')
cf = configparser.ConfigParser()
cf.read('../config/traffic.config')
    

if __name__ == '__main__':
    if os.path.exists(test_img_dir):
        shutil.rmtree(test_img_dir)
    os.makedirs(test_img_dir) 

    if os.path.exists(image_vis_path):
        shutil.rmtree(image_vis_path)
    os.mkdir(image_vis_path)  

    main()
    # 打印样本统计结果，输出详细结果到文件。
    # print('todo. all classes count')
    print('len zero_object_img: ', len(zero_object_img))
    print('len class_not_match: ', len(class_not_match))
    print('len target_num_not_match: ', len(target_num_not_match))

    with open('../output/create_record_log.txt', 'w+') as f:
        f.write(str(zero_object_img))
        f.write(str(class_not_match))
        f.write(str(target_num_not_match))

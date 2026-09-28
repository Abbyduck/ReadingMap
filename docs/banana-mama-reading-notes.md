# 香蕉妈妈资料阅读笔记

这份笔记记录香蕉妈妈本地原图书单的人工读图结果。当前目标是先把资料拆成系统可用的年龄段、主题、素材角色和证据页，而不是一次性追求所有小字 OCR 完成。

## 总体判断

香蕉妈妈资料属于分龄选书地图，核心组织方式是“年龄段 + 主题分类 + 点读/难度提醒”。同一套书在多个年龄段重复出现时，应保留不同年龄上下文，不做推荐关系合并。

可稳定识别的跨图提醒包括：

- 原图大量使用“强推”标记，应进入 `emphasis=强推`。
- “点读”“毛毛虫点读笔”“小达人点读笔”等应进入 `reading_channel` 或 `raw_text`。
- “2.5岁以上”“3.5岁以上”“4.5岁以上”是下限提醒，不应被普通年龄段覆盖。
- “虚构”标注是书单标题的一部分，表示本组偏故事类/虚构类推荐，不是数据质量问题。
- 带 AR、蓝思、牛津树等级的页面，应优先保存原文级别；暂时拿不准数值时先进入 `raw_text`，后续再结构化拆数值。

## 0-2 岁英文绘本书单

页数：3 张。文件名顺序与主题顺序一致。

1. 常识认知：Lift-the-Flap First 100 Words、The Colourful World for Baby、See Touch Feel、Pop and Play、Mommy Daddy、异形翻翻书、Zoe and Zack、水果/蔬菜认知、Me and My、Little Furry Friends、Red Car Green Car。
2. 童谣韵律歌曲/交通工具：Super Simple Songs、鹅妈妈童谣、Llama Llama、培生英文童谣；Goodnight Digger/Tractor、Byron Barton 交通工具、The Wheels on the Trucks、Maisy 交通工具、Car Car Truck Jeep。
3. 互动/游戏书、故事类：手指洞洞书、Pat the Bunny、触摸/翻翻类游戏书；Fun Friends、Tales from Acorn Wood、I Am、Funny Face、古力小超人。

## 2-3 岁英文绘本书单

页数：5 张。已新增 `order.json`，按图内主题逻辑排序为常识认知、童谣/互动、交通/恐龙、故事类1、故事类2。

- 常识认知：Lift-the-Flap First 100 Words、See Touch Feel、Pop and Play、Mommy Daddy、Zoe and Zack、水果/蔬菜认知、Me and My、Little Furry Friends、Red Car Green Car、数字/颜色认知、My First Reading、The World of Worm。
- 童谣/互动：鹅妈妈童谣、Super Simple Songs、培生英文童谣、Llama Llama、My First Music Fun、Busy Fingers、Pat the Bunny、触摸/翻翻游戏书。
- 交通工具/恐龙：Goodnight Digger/Tractor、Byron Barton 交通工具、The Wheels on the Trucks、Maisy 交通工具、Car Car Truck Jeep、Digger/恐龙工程车、I'm the Driver。
- 故事类1：Five Little Monkeys、Fun Friends、Tales from Acorn Wood、I Am、Funny Face、Pip and Posy、Biscuit、Big Steps、Little Hoo、Mr. Panda、Maisy。
- 故事类2：Little Hoo、Mr. Panda、Maisy、Flubby、My First Story、Shh! We Have a Plan、Goose、A Tiny and Friends Book、The Mouse Who、Pete the Cat、Lily and Milo。

## 3-4 岁英文绘本书单

页数：7 张。主题顺序大体为漫画、童谣/魔法探险/经典童话、常识/交通、幽默/互动、故事类1-3。

可确认条目包括：小鱼系列、Best Buddies、形状朋友、Bobo and Pup-pup、Hello Hedgehog、Fox Tails、Bumble and Bee、Yeti、The Gingerbread Man on the Loose、Blippo & Beep；古力小超人、亚瑟系列、Caryl Hart、Usborne Reading Collection；A Pig A Fox、Dave/Dad's Breakfast Blast Off、Molly Mischief、Interrupting Chicken、Jane Clarke、Who's in Your Book、This Book 系列；Pete the Cat、Pip and Posy、Biscuit、Big Steps、Little Hoo、Mr. Panda、Maisy、Flubby、Shh! We Have a Plan、Goose、Rollo、Grumpy Bird、Usborne Fairytale Tales、Penguin、Anuska、Norman、No-Bot、Rory the Dinosaur、Love Monster、Max、Duck & Penguin、The Stormy Whale、Gemma。

## 4-5 岁英文绘本书单

页数：5 张。该年龄段延续 3-4 岁主题，但更强调桥梁前资源和较高难度故事。

可确认条目包括：鹅妈妈童谣、My First Music Fun、经典童话、W-Play、Usborne Reading Collection、Caryl Hart、Fairylight Friends、Nibbles、Supertato、Super Poop、A Pig A Fox、Molly Mischief、Interrupting Chicken、Croc and Ally、Crabby Book、The Dumb Bunnies、Dino Diggers、Nee Naw、Dear Dinosaur、Pete the Cat、Mr. Panda、Maisy、Flubby、My First Story、Goose、The Mouse Who、Lily and Milo、Rollo。

## 5-6 岁英文绘本书单

页数：4 张。当前图组只出现部分主题页，可能不是完整 5-6 岁全集。

可确认条目包括：鹅妈妈童谣、经典童话、W-Play、Usborne Reading Collection、小鱼系列、Best Buddies、形状朋友、Bobo and Pup-pup、Hello Hedgehog、Fox Tails、Bumble and Bee、Yeti、The Gingerbread Man on the Loose、Blippo & Beep、Press Start、Billy and the Mini Monsters、Mighty Robot、Journey to the West、古力小超人、Caryl Hart、Fairylight Friends、Nibbles、Supertato、Super Poop、Let's Get Along、Tom Percival、Katy Hudson、Ricky、Pete the Cat、Shifty McGifty and Slippery Sam、Pumpkin Soup、Princess Series、Dragon Post/Beast Feast/Santa Post、Arfy。

## 6 岁以上英文书单

页数：8 张。主题覆盖桥梁书、初章书、魔法探险、幽默搞笑、交通/恐龙、互动游戏、故事类1-3。

可确认条目包括：Press Start、Billy and the Mini Monsters、Mighty Robot、Journey to the West、Layla、Nate the Great、Captain Awesome、Haggis and Tank、Kung Pow Chicken、Dog Man、Magic Tree House、My Weird School、The Treehouse Collection、牛津树10-12、Caryl Hart、Fairylight Friends、Nibbles、Supertato、Super Poop、A Pig A Fox、Molly Mischief、Interrupting Chicken、Croc and Ally、Crabby Book、The Dumb Bunnies、T-Rex Time Machine、Dino Diggers、Busy Wheels、Dear Dinosaur、Who's in Your Book、Bunny Will、What's Next Door?、This Book、Pete the Cat、Grumpy Bird、A Jack Book、A Pony Named Bonny、You Choose、No-Bot、Rory the Dinosaur、The Stormy Whale、Scaredy Monster、Knuffle Bunny、How to Hide a Lion、Dragon、I Can Read、Charlie and Lola、Tom Percival、Katy Hudson、Pumpkin Soup、Princess Series、Arfy。

## 英语启蒙书单汇总精简版

页数：12 张。它不是分龄单页，而是汇总型入口，适合拆为“初章书、分级书、科普精简书、绘本强推书”四类。

- 初章书：Magic Tree House、My Weird School、The Treehouse Collection、牛津树10-12。
- 分级书：学乐高频词、Buddy Readers、Super Hammy、中信小读者；进阶分级包括牛津树学校版、丽声百科、Highlights 科普、美国分级、牛津树探索、牛津树故事/传统故事等。
- 科普精简书：大猫自然拼读、思维盒子、Do You Know?、水先生、神奇校车、First Science Vocabulary Readers、Look Inside、Jump 系列、Fly Guy Presents、Magic School Bus、Okido、Time for Kids。
- 绘本强推书：鹅妈妈童谣、Super Simple Songs、培生英文童谣、Llama Llama、手指洞洞书、Pat the Bunny、Funny Face、Pip and Posy、Mr. Panda、Maisy、Flubby、Biscuit、Pete the Cat、Grumpy Bird、Scaredy Monster、Maud the Koala、Charlie and Lola、Press Start、Billy and the Mini Monsters、Mighty Robot、Layla、Kung Pow Chicken、Dog Man。

## 2026 牛1-高章泛听泛读书单

页数：6 张。它是等级参照型资料，不适合作为普通年龄段书单。列结构可见为等级、书名、封面、介绍、牛津树/RAZ/AR/蓝思等指标。当前联系表可确认第一阶段包括 Diary of a Wimpy Kid、How to Train Your Dragon、Asterix、Percy Jackson，后续页覆盖牛中、高章前、桥梁与中高章书目。

该组建议在下一轮以单页放大方式逐页 OCR，优先拆 `ort_level_text`、`ar_text`、`lexile_text`，暂不按联系表小图录完整数值。

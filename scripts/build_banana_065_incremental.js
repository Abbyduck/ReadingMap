const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const sourceName = '香蕉妈妈__065__2026年香蕉妈妈牛1-高章泛听泛读书单-小红书.json';
const sourcePath = path.join(root, 'source_data', 'reading_lists', sourceName);
const outputDir = path.join(root, 'source_data', 'drafts', 'reading_lists');
const outputPath = path.join(outputDir, '香蕉妈妈__065__2026年香蕉妈妈牛1-高章泛听泛读书单-小红书__incremental-v2.json');
const original = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));

// 每行：图内页码 § 行号 § 分区 § 音频 § 原始书名 § 原图介绍 § 参考级别 § AR § 蓝思 § 原图标记
const rowsText = `
1§1§牛1-牛4 / Raz C-F§无音频§The Adventure of Otto 机器人奥托的冒险（Ready to Read系列）§搞笑主题，适合自主阅读§牛1-2§0.5-0.9§80-200L§
1§2§牛1-牛4 / Raz C-F§扫码音频；漫画；适合自读§Frog and Dog（漫画）§适合练习CVC拼读§牛2-3§0.6-0.8§50-180L§
1§3§牛1-牛4 / Raz C-F§无音频§Flubby系列§一只傲娇小猫的有趣日常生活§牛1-2§0.6-1.2§140-240L§强烈推荐
1§4§牛1-牛4 / Raz C-F§无音频§Nat the Cat 小猫纳特（Ready to Read系列）§猫和小老鼠的日常故事，适合自主阅读§牛2-3§0.9（只查到3册）§70-210L§
1§5§牛1-牛4 / Raz C-F§无音频§Brownie and Pearl on the Go 女孩和猫咪（Ready to Read系列）§小女孩和小猫咪的日常生活§牛2-3§0.8-1.2§70-290L§
1§6§牛1-牛4 / Raz C-F§有§Biscuit 饼干狗（I Can Read系列）§小女孩和小狗的生活日常§牛2-3§0.7-1.2§BR-290L§
1§7§牛1-牛4 / Raz C-F§无音频§JOJO漂亮的南希初级秀秀（I Can Read系列）§小姐妹的生活日常§牛2-3§1.0-1.3§100-300L§书名原图字样待校对
1§8§牛1-牛4 / Raz C-F§无音频§Otter 水獭系列（I Can Read系列）§宠物小水獭的生活日常§牛2-3§1.2-1.4§160-390L§
1§9§牛1-牛4 / Raz C-F§无音频§Daniel Tiger's Neighborhood 小老虎丹尼尔（Ready to Read系列）§情商社交，有同名动画§牛3-4§1.1-1.4§130-440L§
1§10§牛1-牛4 / Raz C-F§无音频§Everything Goes 交通工具（I Can Read系列）§交通工具主题§牛3-4§0.9-1.3§70-180L§
1§11§牛1-牛4 / Raz C-F§无音频§Ty's Travels 泰的旅行（I Can Read系列）§Ty的日常生活，充满童趣§牛3-4§1.3-1.5§210-280L§
1§12§牛1-牛4 / Raz C-F§漫画；适合自读§小猪小象（漫画）§经典漫画§牛3-5§0.5-1.5§40-330L§
1§13§牛1-牛4 / Raz C-F§无音频§The Little Critters 小毛怪（I Can Read系列）§小毛怪的生活日常，偏情商社交§牛3-5§0.9-1.8§110-440L§
1§14§牛1-牛4 / Raz C-F§有§爆笑英语§比400句简单点儿§牛3-4§-§-§强烈推荐
1§15§牛1-牛4 / Raz C-F§有§儿童英语情境口语400句§通俗易懂，搞笑故事§牛4§-§-§强烈推荐
1§16§牛1-牛4 / Raz C-F§漫画；适合自读§Fox Tails 狐狸尾巴（漫画）§搞笑易懂§牛4-5§1.1-1.6§310-380L§
1§17§牛1-牛4 / Raz C-F§无音频§Pete the Cat 皮特猫 My First（I Can Read系列）§场景丰富，培养乐观精神§牛4-5§1.2-1.9§160-390L§强烈推荐
1§18§牛1-牛4 / Raz C-F§无音频§Pete the Cat 皮特猫 Level 1（I Can Read系列）§场景丰富，培养乐观精神§牛5-6§1.7-2.3§270-540L§强烈推荐
1§19§牛1-牛4 / Raz C-F§无音频§Sabrina Sue Loves to Travel! 爱旅游的小鸡（Ready to Read系列）§小鸡不惧困难，去自己想去的地方§牛4-5§-§-§
1§20§牛1-牛4 / Raz C-F§无音频§Max & Mo 马克斯和莫（Ready to Read系列）§以2只仓鼠（class pets）为主角的校园生活，后附小手工游戏§牛4-5§1.1-1.3（只查到前4册）§180-280L§
1§21§牛1-牛4 / Raz C-F§无音频§Bunny Will 邦尼威尔（Ready to Read系列）§互动书§牛4-5§1.1-1.3（只查到3册）§360-450L§
1§22§牛1-牛4 / Raz C-F§无音频§Adventures in Lego City 乐高城市英雄系列§交通工具主题§牛4-5§-§100-400L§强烈推荐
3§1§牛6-牛9§无音频§Splat the Cat 啪嗒猫（I Can Read系列）§搞笑风格的日常生活§牛6-7§1.8-2.6§300-500L§
3§2§牛6-牛9§无音频§Penny 小老鼠佩妮（I Can Read系列）§温馨，偏女生的日常小故事§牛6-7§1.9-2.6§290-470L§
3§3§牛6-牛9§无音频§Harry the Dog 狗狗哈利（I Can Read系列）§淘气小狗的日常§牛6-7§2.2-2.6§370-470L§
3§4§牛6-牛9§有§Poppleton 小猪波普尔顿§温情故事§牛6-8§1.9-2.7§320-460L§
3§5§牛6-牛9§无音频§Clark the Shark 鲨鱼克拉克（I Can Read系列）§搞笑风格，校园生活为主§牛7§2.3-2.6§430-500L§强烈推荐
3§6§牛6-牛9§有§神奇校车桥梁版§穿越故事，含科普§牛5-8§1.7-2.7§240-510L§强烈推荐
3§7§牛6-牛9§有§Henry and Mudge 亨利与马吉（Ready to Read系列）§男孩亨利与狗的日常生活§牛7§2.2-2.7§370-560L§强烈推荐
3§8§牛6-牛9§无音频§Annie and Snowball 安妮与雪球§亨利表妹安妮的日常生活§牛7-9§2.3-3.0§480-520L§
3§9§牛6-牛9§无音频§Click, Clack, Go! 嘎哈农场系列§脑洞大开的农场故事，荒诞幽默类§牛6-9§1.4-3.1§290-520L§英文书名原图字样待校对
3§10§牛6-牛9§无音频§Molly of Denali 朵拉姐妹篇（I Can Read系列）§探险故事，get探险技能§牛7§2.3-2.7§390-460L§
3§11§牛6-牛9§无音频§My Weird School 疯狂学校（I Can Read系列）§疯狂学校的简单版§牛7§2.2-2.5§430-510L§
3§12§牛6-牛9§有§Flat Stanley 纸片人（I Can Read系列）§桥梁版纸片人，生活故事§牛7§2.2-2.7§410-520L§
3§13§牛6-牛9§有§Zak Zoo 扎克和他的动物家族§夸张搞笑§牛7-9§2.2-2.9§490-580L§强烈推荐
3§14§牛6-牛9§有§Winnie and Wilbur 女巫温妮§夸张搞笑，奇幻魔法§牛7-9§2.3-3.1§-§强烈推荐
3§15§牛6-牛9§有§Mister Shivers 颤抖先生5册§恐怖主题，胆小慎入§牛8§2.5-2.8§460-520L§
3§16§牛6-牛9§有§Frog and Toad 青蛙与蟾蜍§冷笑话式幽默§牛8-9§2.5-2.9§400-480L§强烈推荐
3§17§牛6-牛9§有§胖龙蓝蓝 Dragon§冷笑话式幽默§牛8-9§2.6-3.2§410-510L§强烈推荐
3§18§牛6-牛9§有§冒险故事岛§微缩世界里的闯关故事，难度跨越大§牛3-9（推荐牛6+再入）§-§-§强烈推荐
3§19§牛6-牛9§公众号音频§Olive & Beatrix 奥莉和贝特丽克斯§现实与魔法结合，解决问题§牛9§2.7-2.9§430-540L§
3§20§牛6-牛9§无音频§Junior Monster Scouts 少年怪物童子军§三个小怪物的侦查冒险故事§牛7-9§-§-§
4§1§牛7-牛9+§有§Press Start! 方块兔§游戏里的闯关故事，超赞§牛7-9§2.3-2.9§450-540L§强烈推荐
4§2§牛7-牛9+§有§Missy's Super Duper 米西公主§小女生视角的校园生活§牛7-9§2.2-3.0§500-540L§
4§3§牛7-牛9+§有§Curious George Classic Collection 好奇猴原版§经典故事，温馨搞笑§牛7-9§2.6-4.1§400-660L§
4§4§牛7-牛9+§动画片+音频§Journey to the West 西游记§先中文再英文，可尝试裸听§牛9+§3.4§500L左右§强烈推荐
4§5§牛7-牛9+§动画片+音频§Rocket Girl 火箭女孩§英雄女孩，拯救世界§牛9+§3.0§500L左右§强烈推荐
4§6§牛7-牛9+§动画片+音频§Rocket Girl's Journey to the West 火箭女孩西游记§古今英雄结合，连续的穿越故事§牛9+§3.2§400-600L§强烈推荐
4§7§牛7-牛9+§漫画；适合自读§Pizza and Taco（漫画）§搞笑漫画§牛6-7§1.8-2.6§100-370L§
4§8§牛7-牛9+§漫画；适合自读§Mr. Wolf's Class（漫画）§大写字体§牛6-7§2.1-2.4§300-490L§
4§9§牛7-牛9+§漫画；适合自读§Catwad（漫画）§大写字体§牛7§2.2-2.6§390-540L§
4§10§牛7-牛9+§有§Mighty Robot 威猛机器人§机器人和小老鼠拯救世界§牛9+§2.9-4.1§520-640L§强烈推荐
4§11§牛7-牛9+§无音频§Billy and the Mini Monsters 比利和小怪兽§小怪兽们闯进生活，麻烦笑料不断§牛8§2.5-2.8§500-560L§强烈推荐
4§12§牛7-牛9+§无音频§Gordon 坏鹅戈登§坏鹅变好鹅§牛9+§2.8§400-600L§
4§13§牛7-牛9+§有§Hamster Holmes 仓鼠福尔摩斯§入门级别破案小故事§牛9+§3.0-3.5§520-610L§
4§14§牛7-牛9+§有§Hot Dog 腊肠狗§社交友谊，幽默搞笑§牛9+§2.7-3.4§550-650L§
4§15§牛7-牛9+§有§Nate the Great 大侦探内特§轻侦探，逻辑推理§牛6-10§2.0-3.2§280-570L§
4§16§牛7-牛9+§有§Layla and the Bots 莱拉和机器人§用科学方法解决问题§牛8-9§2.5-2.9§500-570L§
4§17§牛7-牛9+§有§小猪梅西 Mercy Watson§生活主题，幽默滑稽§牛8-9§2.6-3.2§450-550L§强烈推荐
4§18§牛7-牛9+§有§Owl Diaries 猫头鹰日记§女孩反馈更喜欢§牛9+§2.5-3.6§330-620L§强烈推荐；女孩
4§19§牛7-牛9+§有§The Princess in Black 黑衣公主§是公主也是黑衣英雄（故事不难，个别词汇难）§牛9+§3.0-3.6§500-560L§强烈推荐
4§20§牛7-牛9+§漫画；适合自读§Dog Man（漫画）§经典漫画§牛7§2.3-2.7§210-550L§
5§1§牛8-牛9+§漫画；适合自读§Max Meow（漫画）§获得超能力，变身超级英雄§牛8-9§2.5-2.8§190-350L§
5§2§牛8-牛9+§有§Haggis and Tank 哈吉斯坦克§搞笑滑稽的想象之旅§牛8-9§2.5-3.1§430-500L§
5§3§牛8-牛9+§公众号音频§Princess Pink and the Land of Fake-Believe 粉红公主与虚无世界§一脚踏进虚假的童话世界§牛9+§2.8-3.2§410-570L§
5§4§牛8-牛9+§音频不全§Bad Guys 坏蛋联盟§坏蛋拯救世界，认知要求高（有同名电影）§牛7-9§2.2-2.9§260-560L§强烈推荐
5§5§牛8-牛9+§有§Kung Pow Chicken 宫保鸡丁§超能鸡拯救世界，听力难度系数高§牛9+§2.9-3.2§550-580L§强烈推荐
5§6§牛8-牛9+§有§First Greek Myths 希腊神话故事§了解神话背景§牛9+§2.8-3.6§550-660L§强烈推荐
5§7§牛8-牛9+§公众号音频§神奇校车25周年动画版-12册§故事里穿插科普§牛9+§3.1-4.3§420-670L§
5§8§牛8-牛9+§公众号音频§神奇校车经典版-6册§科普知识点多，较难§牛9+§3.6-4.6§500-730L§
5§9§初章入门§有§Monkey Me 猴子男孩§生活+夸张，激动就变猴子抓坏蛋§§2.2-2.5§490-510L§
5§10§初章入门§有§Pixie Tricks 小精灵诡计§魔法主题§§2.5-2.9§440-520L§
5§11§初章入门§有§Junie B. Jones 朱妮琼斯§幼儿园大班-小学，写实校园生活§§2.7-3.0§340-540L§
5§12§初章入门§有§Rabbit & Bear 胖熊和瘦兔§友谊故事，偏温情类§§2.8-3.4§480-570L§
5§13§初章入门§有§Dory Fantasmagory 多莉幻想曲§生活+想象，视角特殊§§2.9-3.2§550-650L§
5§14§初章入门§有§Rainbow Magic 彩虹魔法仙子系列§魔法主题§§3.3-3.9§620-660L§
5§15§初章入门§有§Isadora Moon 伊莎多拉混恩系列§生活+魔法，一半吸血鬼一半小仙子§§3.3-4.1§520-710L§中文书名原图字样待校对
5§16§初章入门§无音频§Desmond Cole Ghost Patrol 捉鬼小分队§生活+悬疑，微恐§§3.5-4.2§600-680L§
5§17§初章入门§有§The Zack Files 扎克档案§生活+悬疑，微恐§§2.7-3.9§370-570L§
5§18§初章入门§-§Magic Tree House 神奇树屋漫画版§借助画面帮助入章§§2.0-2.4§330-530L§
5§19§初章入门§有§神奇树屋 Magic Tree House§奇幻类穿越故事§§2.6-3.7§380-590L§
5§20§初章入门§有§驯龙大师 Dragon Master§奇幻类故事§§3.1-4.2§490-600L§
7§1§初章→中章过渡§有§Merlin Mission 梅林任务§神奇树屋第二部§§3.5-4.2§460-600L§
7§2§初章→中章过渡§有§老鼠记者 Geronimo Stilton§惊险刺激的冒险之旅§§3.1-3.8（不同套系值不同）§410-570L（不同套系值不同）§
7§3§初章→中章过渡§有§The Secret Explorers DK秘密探险家§故事里穿插科普，高级版超级飞侠§§4.2-4.6§580-650L§
7§4§初章→中章过渡§无音频§Football Super Stars 足球明星§顶级足球明星的成长和战绩§§4.6-6.4§730-940L§
7§5§初章→中章过渡§有§Sherlock Holmes 16 Books Collection 大侦探福尔摩斯探案集§福尔摩斯青少版§§3.1-7.4§560-1000L§
7§6§初章→中章过渡§有§Tom Gates 了不起的小盖茨系列§小学生日记，插画丰富§§3.8-4.4§610-720L§
7§7§初章→中章过渡§有§Big Nate系列三册§六年级男孩的日记§§2.9-3.1§430-520L§
7§8§初章→中章过渡§-§I Survived 幸存者漫画版§漫画版§§2.7-3.6§390-570L§
7§9§初章→中章过渡§有§I Survived 幸存者章节书§回忆历史灾难事件§§3.8-5.1§550-740L§
7§10§中章§有§Captain Underpants 内裤超人§夸张搞笑校园生活，全彩内页§§4.3-5.5§710-890L§
7§11§中章§有§The World's Worst Children 世界上糟糕的孩子3册§超级夸张无厘头§§4.7-5.3§670-760L§
7§12§中章§有§Roald Dahl 罗尔德达尔 原版§罗尔德达尔作品合集§§3.1-6.1§560-1080L§
7§13§中章§有§Amelia Fang 阿米莉亚芳§魔法冒险§§4.4-5.1§710-780L§
7§14§中章§有§The Wild Robot 荒野机器人3册§中章入门，不卡认知§§5.1-5.5§720-840L§
7§15§中章§有§Percy Jackson 波西杰克逊§希腊神话与现代生活结合§§4.1-4.6§590-680L§
7§16§中章§有§Wings of Fire 火翼飞龙§龙族的奇幻故事§§5.0-5.6§710-790L§
7§17§中章§有§Peanut Jones 花生琼斯3册§用画笔开启冒险之旅§§5.1-5.6§800-860L§
7§18§中章§有§The Beast and the Bethany 怪兽与贝萨妮§欲望和人性的对抗§§5.3-6§730-890L§
8§1§高章§有§Diary of a Wimpy Kid 小屁孩日记§§§5.2-6.2§910-1060L§
8§2§高章§无音频§How to Train Your Dragon 驯龙高手§§§6.2-6.9§910-1070L§
8§3§高章§有§Adam Kay 亚当凯系列§§§6.1§910-1060L§
8§4§高章§有§Harry Potter 哈利波特7册§§§6.0-7.2§880-950L§
8§5§纽伯瑞获奖作品§有§Because of Winn-Dixie 傻狗温迪克（2001年银奖）§关于友谊、原谅和救赎§§3.9§670L§
8§6§纽伯瑞获奖作品§有§Charlotte's Web 夏洛的网（1953年银奖）§关于友谊和成长§§4.4§680L§
8§7§纽伯瑞获奖作品§有§Holes 别有洞天（1999年金奖）§有深度，适合初中生§§4.6§660L§
8§8§纽伯瑞获奖作品§有§Walk Two Moons 印第安人的麂皮靴（纽伯瑞金奖）§共情力养成，适合初中生§§4.9§770L§
8§9§纽伯瑞获奖作品§有§Wonder 奇迹男孩（非获奖作品，但推荐）§好读，适合五六年级§§4.8§790L§
`.trim();

const rows = rowsText.split('\n').map((line) => {
  const [page, row, section, audio, title, intro, level, ar, lexile, flags] = line.split('§');
  return { page: Number(page), row: Number(row), section, audio, title, intro, level, ar, lexile, flags };
});

const sourceDoc = original.creator.other_info.source_documents.find((doc) => doc.title === original.list.title);
const actualPageToAssetIndex = new Map([[8, 0], [1, 1], [3, 2], [4, 3], [5, 4], [7, 5]]);
const assetFor = (page) => sourceDoc.pages[actualPageToAssetIndex.get(page)];
const metric = (raw) => {
  const normalized = !raw || raw === '-' ? null : raw;
  if (!normalized) return { raw: null, value: null, min: null, max: null };
  const numbers = [...normalized.matchAll(/\d+(?:\.\d+)?/g)].map((match) => Number(match[0]));
  if (!numbers.length) return { raw: normalized, value: null, min: null, max: null };
  if (normalized.includes('-') && numbers.length >= 2) return { raw: normalized, value: null, min: numbers[0], max: numbers[1] };
  return { raw: normalized, value: numbers[0], min: null, max: null };
};

const legacyAnchors = ['Diary of a Wimpy Kid', 'How to Train Your Dragon', 'Asterix', 'Percy Jackson', 'Because of Winn-Dixie', 'Out of My Mind', 'Wonder'];
const isLegacyAnchor = (title) => legacyAnchors.some((anchor) => title.toLowerCase().startsWith(anchor.toLowerCase()));
const stageFor = (row) => ({
  stage_order: row.page,
  title: `原图第${row.page}页：${row.section}`,
  description: `按原图第${row.page}页第${row.row}行增量转录`,
  recommended_age_min_months: null,
  recommended_age_max_months: null,
  level_system: row.level ? 'Oxford Reading Tree reference' : null,
  level_value_min: null,
  level_value_max: null,
  source_page_label: `第${row.page}页`,
});

const items = rows.map((row, index) => {
  const asset = assetFor(row.page);
  const notes = ['本条仅做原图转录，尚未执行联网 Research。'];
  if (row.flags) notes.push(row.flags);
  return {
    sequence: index + 1,
    position: row.row,
    raw_title: row.title,
    extracted: {
      title: row.title,
      recommended_age: null,
      ar: metric(row.ar),
      lexile: metric(row.lexile),
      level: row.level || null,
      comment: row.intro || null,
      note: `音频：${row.audio || '原图未标注'}；原图第${row.page}页第${row.row}行${row.flags ? `；${row.flags}` : ''}`,
      other_info: {
        stage: stageFor(row),
        audio_text: row.audio || null,
        source_section: row.section,
        source_page_label: `第${row.page}页`,
        source_row: row.row,
        source_evidence: {
          ...asset,
          source_page_label: `第${row.page}页`,
          source_row: row.row,
        },
        transcription_status: row.flags.includes('待校对') ? 'needs_text_check' : 'confirmed_from_available_image',
        incremental_v2: true,
      },
    },
    analysis: {
      possible_entity_type: 'series',
      confidence: 0.6,
      notes,
      other_info: {
        research_status: 'not_started',
        review_status: 'pending',
        legacy_anchor_reused: isLegacyAnchor(row.title),
      },
    },
  };
});

for (const title of ['Asterix', 'Out of My Mind']) {
  const old = original.items.find((item) => item.raw_title === title);
  items.push({
    ...old,
    sequence: items.length + 1,
    position: null,
    extracted: {
      ...old.extracted,
      note: '沿用旧版7条锚点；本地缺少原图第2、6页，当前无法定位，待补原图后校对。',
      other_info: {
        ...old.extracted.other_info,
        stage: {
          stage_order: 9,
          title: '旧版锚点：缺页待补证',
          description: '本地仅有第1、3、4、5、7、8页；此条沿用旧版识别，不新增推测。',
          recommended_age_min_months: null,
          recommended_age_max_months: null,
          level_system: null,
          level_value_min: null,
          level_value_max: null,
        },
        source_evidence: null,
        transcription_status: 'missing_source_page_needs_evidence',
        incremental_v2: true,
      },
    },
    analysis: {
      ...old.analysis,
      confidence: Math.min(old.analysis.confidence, 0.5),
      notes: ['沿用旧版锚点；本地缺第2、6页，尚未从现有原图复核。'],
      other_info: {
        ...old.analysis.other_info,
        research_status: 'not_started',
        review_status: 'needs_source_evidence',
        legacy_anchor_reused: true,
      },
    },
  });
}

const stages = [...new Map(items.map((item) => [item.extracted.other_info.stage.title, item.extracted.other_info.stage])).values()];
const output = {
  ...original,
  list: {
    ...original.list,
    description: '对本地现有第1、3、4、5、7、8页原图做增量重新识别；原文件不覆盖，缺第2、6页。当前仅完成来源事实转录，待 Codex Research 与人工审核。',
    other_info: {
      ...original.list.other_info,
      updated_at: '2026-09-16T00:00:00+08:00',
      stages,
      position_scope: 'source_page',
      incremental_reextraction: {
        version: 2,
        scope: 'single_reading_list_only',
        original_file_preserved: true,
        available_source_pages: [1, 3, 4, 5, 7, 8],
        missing_source_pages: [2, 6],
        confirmed_items_from_images: rows.length,
        carried_legacy_items_needing_source_evidence: 2,
        research_status: 'not_started',
      },
    },
  },
  items,
};

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({ outputPath, confirmedItems: rows.length, totalItems: items.length, missingPages: [2, 6] }, null, 2));

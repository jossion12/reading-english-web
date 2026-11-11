-- =============================================================================
-- Reading-English-Web · 种子数据
-- 用于本地开发 / 前端联调 / RLS 权限验证
--
--   · 3 条素材梗概（source_log）
--   · 7 篇文章（articles）：覆盖 L1/L2/L3、四大主题、四种文体、多发布日
--   · 其中 1 篇 is_published = false —— 用于验证 anon 角色读不到草稿
-- =============================================================================

insert into public.source_log (source_fingerprint, source_summary, remark)
values
  (
    'a1f3c9d2e7b84506af19d3c6b8e27f104a5b6c7d8e9f0a1b2c3d4e5f60718293',
    E'新闻标题：贵州山区女教师雨雪天徒步翻山到学生家中家访\n核心事实：贵州省黔东南某山区小学教师李雨在暴雪天气独自徒步三小时，翻越两座山头，到学生家中进行家访并送上课本。\n背景意义：乡村教育工作者在恶劣天气下仍坚持家访，保障了偏远山区学生不因天气缺课。\n正向导向：展现教师的责任心与奉献精神，引导学生理解什么是真正的关爱与坚持。\n禁止加入内容：不得编造教师姓名、学校名称、受访学生家庭细节；不得夸大或加入伤亡、补助金额等原文没有的信息。',
    '示例素材 #1 · 来源：新华社 2026-10-20（演示用虚构内容）'
  ),
  (
    'b2e4d0a3f8c95617b02a4d7c9f38a215b6c7d8e9f0a1b2c3d4e5f6071829304',
    E'新闻标题：城市社区建起共享书屋，居民可自助借还\n核心事实：某市老城区在社区服务中心设立24小时共享书屋，居民凭手机扫码即可自助借阅，每本书可借阅三十天。\n背景意义：社区通过共享书屋降低阅读门槛，让居民在步行范围内就能接触到纸质书籍。\n正向导向：倡导日常阅读与邻里互助，呼应建设书香社会的主题。\n禁止加入内容：不得虚构具体书名、捐赠方、阅读人数；不得加入评测或商业推广信息。',
    '示例素材 #2 · 来源：人民网 2026-10-22（演示用虚构内容）'
  ),
  (
    'c3f5e1b4a9d06728c13b5e8d0f49b326c7d8e9f0a1b2c3d4e5f607182930415',
    E'新闻标题：研究团队用卫星观测记录到候鸟迁徙新路线\n核心事实：研究团队连续三年利用卫星定位器追踪一批候鸟，发现它们在迁徙途中新增了一条经过高原湖泊的路线，比传统路线缩短约两天。\n背景意义：新路线的发现为鸟类保护和迁徙监测提供了数据支持。\n正向导向：呈现科学探索的价值，强调长期观察与数据积累的意义。\n禁止加入内容：不得编造具体物种名称、湖泊名称、湖泊所在国家；不得给出未经证实的生态影响结论。',
    '示例素材 #3 · 来源：央视新闻 2026-10-25（演示用虚构内容）'
  )
on conflict (source_fingerprint) do nothing;

-- ---------------------------------------------------------------- articles --
-- 整段包在 DO 块里：种子文章已存在则整段跳过。
-- 这样 `supabase stop` → `supabase start` 重新执行本文件时不会插出重复文章。
do $$
begin
  if exists (select 1 from public.articles where title_en = 'The Rainy Walk to School') then
    return;
  end if;

-- L1 · 记叙文 · 人与自我
insert into public.articles (
  publish_date, title_en, title_cn, level, theme, sub_theme, style, color_tag,
  english_paras, chinese_paras, "sort", is_published, source_id
) values (
  '2026-10-26',
  'The Rainy Walk to School',
  '雨天的上学路',
  'L1',
  '人与自我',
  '坚持与责任',
  '记叙文',
  '#E8F1FF',
  '[
    "It was raining hard on Monday morning. My teacher Ms. Li did not come to school. At nine o''clock, we waited and looked at the door. Then our head teacher came in. She said Ms. Li was visiting a sick student at home.",
    "The student lives near a mountain. The road is long and steep. Ms. Li walked there in the rain. She came back at noon. Her shoes were full of mud, but she smiled and said the student was fine.",
    "We were quiet for a while. Then Tom said, \"Walking in the rain is hard, but she went.\" After school, three of us cleaned her classroom. We wanted to do something small for her."
  ]'::jsonb,
  '[
    "星期一早晨雨下得很大。李老师没有来学校。九点钟，我们一直望着门口张望。后来，校长走进来，说李老师去学生家里看望一位生病的学生了。",
    "那位同学住在山边，路很长，也很陡。李老师冒雨走了过去。中午她回来了，鞋上全是泥，但她笑着说那位同学没事。",
    "我们安静了一会儿。然后汤姆说：\"雨中走路很辛苦，但她还是去了。\"放学以后，我们三个人把她的教室打扫干净。我们想为她做点小事。"
  ]'::jsonb,
  1,
  true,
  (select id from public.source_log where source_fingerprint = 'a1f3c9d2e7b84506af19d3c6b8e27f104a5b6c7d8e9f0a1b2c3d4e5f60718293' limit 1)
);

-- L1 · 说明文 · 人与自然
insert into public.articles (
  publish_date, title_en, title_cn, level, theme, sub_theme, style, color_tag,
  english_paras, chinese_paras, "sort", is_published, source_id
) values (
  '2026-10-26',
  'How a Raindrop Comes Back',
  '雨滴如何回到天上',
  'L1',
  '人与自然',
  '水循环',
  '说明文',
  '#E3F7EC',
  '[
    "Water is never still. The sun warms the sea and the water on the ground. It rises into the air as vapor. This is called evaporation.",
    "High in the sky, the air is cold. The vapor turns back into tiny drops of water. Many drops together make a cloud. When the drops become heavy, they fall down as rain.",
    "The rain goes into rivers and back to the sea. Then the whole cycle starts again. The water you drink today may have fallen as rain many years ago."
  ]'::jsonb,
  '[
    "水从不停歇。太阳晒热海洋和地面上的水，水就变成水蒸气升到空中，这叫做蒸发。",
    "在高高的天上，空气很冷，水蒸气又变回一颗颗小水滴。无数小水滴聚在一起就是云。小水滴变重了，就作为雨落下来。",
    "雨水流进河流，又回到海里，然后整个循环重新开始。你今天喝到的水，很可能在很多年前就曾是一场雨。"
  ]'::jsonb,
  2,
  true,
  null
);

-- L2 · 记叙文 · 人与社会
insert into public.articles (
  publish_date, title_en, title_cn, level, theme, sub_theme, style, color_tag,
  english_paras, chinese_paras, "sort", is_published, source_id
) values (
  '2026-10-27',
  'The Bookshelf That Changed a Street',
  '改变了整条街的书架',
  'L2',
  '人与社会',
  '邻里互助',
  '记叙文',
  '#FFF4E0',
  '[
    "When the old bookshop closed last spring, Mr. Green felt that something was lost from his street. He had bought every schoolbook for his daughter there, and the owner had once lent him a novel when he could not afford to buy it.",
    "So Mr. Green put twelve books on a shelf outside his gate and wrote a note on the lid: \"Take one, leave one.\" At first, only a few neighbours used the shelf. A student took a grammar book and left a story about a lost dog. Soon the shelf held forty books, and a retired teacher began cleaning it every morning.",
    "This year the street held a small festival near the shelf. People brought food, children read aloud on the steps, and the new owner of the bookshop came to sell books at a low price. Mr. Green did not expect twelve books to change so much, but he now keeps a small chair by the shelf, and people often sit there to talk."
  ]'::jsonb,
  '[
    "去年春天老书店关门的时候，格林先生觉得自己的街上少了一点什么。他女儿所有的课本都在那儿买的，书店老板还曾在他买不起的时候借给他一本小说。",
    "于是格林先生把十二本书摆在大门外的架子上，在盒盖上写了一张纸条：\"拿一本，留一本。\"起初只有少数邻居来光顾。一位学生拿走了一本语法书，留下一则关于走失小狗的故事。不久架子上有了四十本书，一位退休老师开始每天早上打扫它。",
    "今年街上在书架旁举办了一场小庙会。人们带来食物，孩子在台阶上大声朗读，新书店老板也来低价卖书。格林先生没想到十二本书能带来这么多变化，如今他在书架旁放了一把小椅子，人们常坐在那里聊天。"
  ]'::jsonb,
  1,
  true,
  (select id from public.source_log where source_fingerprint = 'b2e4d0a3f8c95617b02a4d7c9f38a215b6c7d8e9f0a1b2c3d4e5f6071829304' limit 1)
);

-- L2 · 应用文 · 人与科技
insert into public.articles (
  publish_date, title_en, title_cn, level, theme, sub_theme, style, color_tag,
  english_paras, chinese_paras, "sort", is_published, source_id
) values (
  '2026-10-27',
  'A Letter to the Exchange Club',
  '给交换社的一封信',
  'L2',
  '人与科技',
  '校园科学节',
  '应用文',
  '#F0E9FF',
  '[
    "Dear Members of the Exchange Club,",
    "Our class is preparing a small science exhibition for the coming Friday. We have built a model that shows how water moves from a leaf to the air, and we would love to explain it to younger students. If your club is free that afternoon, we would be glad to welcome you at our classroom, Room 204, at two o''clock.",
    "We will show three short experiments, and there will be a small poster show about the birds we tracked with old cameras. Please let us know by Thursday if you can come. We hope the exchange will make the day warmer for everyone.",
    "Yours sincerely,\nClass 3, Grade 7"
  ]'::jsonb,
  '[
    "亲爱的交换社成员：",
    "我们班正在为本周五准备一场小型科学展。我们做了一个展示水如何从叶子移动到空气中的模型，很愿意给低年级的同学讲解。如果贵社当天下午有空，我们欢迎您于两点到我们教室 204 来。",
    "我们将展示三个小实验，还会办一个小型海报展，展出我们用旧相机记录的鸟类。请在周四前告诉我们你们能否前来，希望这次交流让大家都度过温暖的一天。",
    "此致敬礼\n七年级三班"
  ]'::jsonb,
  2,
  true,
  null
);

-- L3 · 议论文 · 人与自然
insert into public.articles (
  publish_date, title_en, title_cn, level, theme, sub_theme, style, color_tag,
  english_paras, chinese_paras, "sort", is_published, source_id
) values (
  '2026-10-28',
  'Small Actions, Long Distance',
  '微小的行动，长远的距离',
  'L3',
  '人与自然',
  '气候变化与日常选择',
  '议论文',
  '#E6F7F4',
  '[
    "When people talk about protecting the environment, the scale of the discussion can feel too large to touch. A single student cannot change the climate, and a single reusable bottle will not cool the planet. Because of this, many people conclude that personal actions are pointless, and they wait for governments and companies to solve the problem instead.",
    "That conclusion is mistaken, although the error is easy to understand. Real change rarely arrives as one dramatic event. It accumulates quietly, and its first stage is usually small and ordinary: a family that starts sorting rubbish, a school that turns off unused lights, a group of neighbours who plant trees along a road that nobody cared about before. None of these actions is impressive alone. Together, however, they change what a community believes is normal, and what people consider possible.",
    "There is a second reason why personal action matters. Every large decision is made by people who first had a chance to practise it. A child who has carried a shopping bag home many times is more likely to question why a plastic bag is given away at the counter. Habits are not only formed by habit; they are formed by reasoning, and by practice given to the reasons we find convincing. To argue that waiting is the only sensible choice is therefore to give up the very thing that makes later change possible.",
    "None of this means that personal effort replaces public action. Rules, research, and fair pricing are still necessary, because a family should not have to pay the whole cost of protecting a shared world. But the two are not rivals. Individual effort is not a substitute for policy; it is what turns policy into something that people actually live. The distance between a comfortable habit and a better one is not very far. It is only a few steps, taken again and again, and they can be taken by anyone."
  ]'::jsonb,
  '[
    "人们谈论保护环境时，讨论的规模常常大得让人无从下手。单个学生改变不了气候，一个可重复使用的水杯也不会让地球变凉。正因如此，许多人得出结论说个人行动毫无意义，于是等着政府和公司去解决。",
    "这个结论是错的，尽管这个错误很容易理解。真正的改变很少以某一次震撼性事件的形式到来。它是安静地累积起来的，而最初的一步通常微小而平凡：一个开始垃圾分类的家庭，一所会关掉无人使用的灯的学校，一群沿着无人关心的大路种树的邻居。这些行动单独看都不算什么，但合在一起，它们会改变一个社区认为什么是正常的，也会改变人们认为什么是可能的。",
    "个人行动之所以重要，还有第二个原因。每一次重大决策，都是由那些事先有机会实践过它的人做出的。一个多次提着购物袋回家的孩子，更可能追问为什么柜台要免费发放塑料袋。习惯不只是被习惯塑造的，它也是被思考塑造的，被那些让我们觉得有说服力的理由所实践的。因此，认为等待是唯一明智选择的人，恰恰放弃了让日后改变成为可能的那件事。",
    "这并不是说个人努力可以取代公共行动。规则、研究和公道的价格依然必要，因为一个家庭不该独自承担保护这个共有世界的全部成本。但两者并不是对手。个人努力不是政策的替代品，它让政策真正成为人们生活的一部分。从一个舒服的习惯到一个更好的习惯之间的距离并不远，不过就是几步路，一遍又一遍地走，而且任何人都可以走。"
  ]'::jsonb,
  1,
  true,
  (select id from public.source_log where source_fingerprint = 'c3f5e1b4a9d06728c13b5e8d0f49b326c7d8e9f0a1b2c3d4e5f607182930415' limit 1)
);

-- L3 · 记叙文 · 人与科技
insert into public.articles (
  publish_date, title_en, title_cn, level, theme, sub_theme, style, color_tag,
  english_paras, chinese_paras, "sort", is_published, source_id
) values (
  '2026-10-28',
  'Three Summers with a Camera on a Bird',
  '与一只鸟的三个夏天',
  'L3',
  '人与科技',
  '科学观察与记录',
  '记叙文',
  '#FFE9EC',
  '[
    "When my grandfather first tied a small camera to a bird, I thought it was a game. The bird was a young swallow that had nested under our eaves, and the camera was no bigger than a sugar cube. Every few seconds it took a picture, and every few minutes it sent the pictures to a box in the forest, where a team downloaded them.",
    "The first summer, the team gave us nothing to look at but rain. The next summer, they found the bird had flown north, and our family, who had lived by the same house for forty years, finally saw where the winters were spent. The third summer they found it near a lake on the highland, and my grandfather, who was too ill to travel, studied the photographs by the window and named the route on an old map.",
    "What stayed with me was not the data but the waiting. For three summers nothing happened, and my grandfather kept trimming the map and replacing the batteries. He used to say that the camera could only record what we were patient enough to let it record. When the third set of pictures arrived, we understood that he had been right, and that the birds had been telling us the same thing for years."
  ]'::jsonb,
  '[
    "当爷爷第一次把一个小相机绑在鸟身上时，我以为这只是一场游戏。那是一只在我们屋檐下筑巢的年轻燕子，相机不过一颗方糖大小。它每隔几秒拍一张照片，每隔几分钟把照片传到森林里的一个箱子上，由一个团队下载下来。",
    "第一个夏天，团队能给我们看的只有雨。第二个夏天，他们发现这只鸟飞向了北方，而我们在这栋房子里住了四十年的家人，第一次看到了它过冬的地方。第三个夏天，他们发现它出现在高原上的一个湖泊旁，而身体已不宜出行的爷爷，就着窗边的光研究那些照片，并在一张旧地图上标出了那条路线。",
    "让我记住的不是数据，而是等待。三个夏天里什么都没发生，爷爷却一直在修地图、换电池。他常说，相机只能记录下我们足够有耐心让它记录的东西。当第三批照片送到时，我们明白了他是对的，而且这些年，这只鸟一直在用同样的方式告诉我们同一件事。"
  ]'::jsonb,
  2,
  true,
  null
);

-- ---- 未发布草稿：用于验证 anon 角色读不到 is_published = false 的行 -----------
insert into public.articles (
  publish_date, title_en, title_cn, level, theme, sub_theme, style, color_tag,
  english_paras, chinese_paras, "sort", is_published, source_id
) values (
  '2026-10-29',
  'Draft: The Library at Night',
  '草稿：夜晚的图书馆',
  'L2',
  '人与社会',
  '公共空间',
  '记叙文',
  '#F5F5F5',
  '[
    "This article has not been published yet. It exists only to prove that the anonymous frontend role cannot read unpublished rows."
  ]'::jsonb,
  '[
    "本文尚未发布，仅用于验证前端匿名角色读不到未发布的文章。"
  ]'::jsonb,
  1,
  false,
  null
);

end $$;

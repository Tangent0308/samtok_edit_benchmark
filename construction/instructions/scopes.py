"""Chinese semantic scope strings; these never identify a hidden source instance."""

BASE = dict(
    line.split("|", 1)
    for line in """legs|支腿
armrests|扶手
doors|柜门
drawer fronts|抽屉面板
front legs|前腿
handles|把手
narrow side panels|窄侧板
shades|灯罩
side panels|侧板
sleeves|袖子
blades|扇叶
front legs|前腿
long rim edges|长边缘
sweater sleeves|毛衣袖子
wheels|车轮
wicker drawer fronts|藤编抽屉面板
wings|机翼
apron|裙板
articulated arm|关节支臂
back panel|背板
backrest|椅背
backrest and its curved support|靠背及其弯曲支架
backrest covering|椅背套
base cabinet below the television screen|电视屏幕下方的底柜
belt strap|腰带带身
blade|刀刃
body|主体
bottom drawer front|底部抽屉面板
bottom edge|底部边缘
bottom storage drawer front|底部储物抽屉面板
branching stems|分叉灯杆
brim|帽檐
cap|盖子
cap collar below the pump|泵头下方的瓶盖圈
circular foot|圆形底座
closed lid|合上的盖板
column|灯柱
conical shade|锥形灯罩
cover|封面
curved lid|弧形盖子
curved seat apron|弧形座椅裙边
curved shade|弧形灯罩
cylindrical body|圆筒形桶身
dark sleeve section behind the striped cuff|条纹袖口后方的深色袖子部分
decorated door panel|带装饰的门板
decorative column|装饰灯柱
detached lampshade|拆下的灯罩
diagonal bag strap|斜向包带
door|柜门
drawer front|抽屉面板
entire visible folded towel|整条可见的折叠毛巾
entire visible glass, excluding any hidden foot|玻璃杯的全部可见部分
entire visible scarf|整条可见围巾
entire visible towel|整条可见毛巾
entire visible wine glass|整只可见葡萄酒杯
exposed blade|裸露的刀刃
exposed curved front leg|裸露的弯曲前腿
exposed footboard rail and its two posts|裸露的床尾横栏及两根立柱
exposed front leg|裸露的前腿
exposed handle|裸露的柄
exposed inner sloping rim|裸露的内侧斜缘
exposed side|裸露的侧面
exposed tabletop|裸露的桌面
exposed thin outer edge|裸露的细外缘
exposed top|裸露的桌面
exterior back panel|外侧背板
faucet|水龙头
front bumper|前保险杠
front of the open upper drawer|拉开的上层抽屉面板
front panel|前面板
glass top|玻璃桌面
handle|把手
headboard|床头板
headboard including its two rear posts|床头板及两根后床柱
hood|引擎盖
housing|外壳
indicated drawer front|指定的抽屉面板
indicated lower door|指定的下柜门
indicated small drawer front|指定的小抽屉面板
knife handle|刀柄
label panel|标签
lid|盖子
long handle|长柄
lower side wall|下部侧壁
middle side wall|中段侧壁
mirror housing|侧视镜外壳
narrow stem|细灯杆
neck|瓶颈
nozzle cap|尖嘴盖
opaque door frame surrounding the viewing window|观察窗周围的不透明门框
ornate base|雕花底座
outer cover|外壳
outer lid|外侧顶盖
outer rim|外缘
outer side panel|外侧面板
outside body|外侧主体
pump head|泵头
raised lid|竖起的盖板
rear bumper|后保险杠
rectangular front label panel|正面的长方形标签
rectangular mirror housing|矩形侧视镜外壳
ribbed outside|带筋纹的外侧
rim|边缘
rounded body|圆腹主体
shade|灯罩
side straps around the visible ear|可见耳朵周围的侧带
side wall|侧壁
solid side panel|实心侧板
strap|背带
support arms|支臂
tall backrest|高椅背
thin inner trim|细内饰边
thin outer rim|细外缘
thin rim|细边缘
thin vertical stem|细竖直灯杆
thin visible rim|可见的细边缘
three back cushions|三块靠背垫
three drawer fronts|三块抽屉面板
three visible legs|三条可见支腿
top rim|顶沿
top surface|桌面
triangular lid|三角形盖子
two back cushions|两块靠背垫
two visible doors|两扇可见柜门
two visible drawer fronts|两块可见抽屉面板
two visible supporting legs|两条可见支腿
uncovered right armrest|未被遮盖的右扶手
upper drawer front|最上层抽屉面板
upper two drawer fronts|最上方的两块抽屉面板
upward-facing shade|向上开口的灯罩
vertical column|竖直灯柱
vertical pipe|竖直灯杆
apron along the curved front edge|弧形前沿的裙板
armrest|扶手
back casing|背壳
back cover|后盖
bag body|包身
bottom panel|底板
central leg|中央支腿
computer tower case|电脑主机机箱
curved leg frame|弯曲支腿框架
frame|边框
front apron|前裙板
headboard|床头板
inner sloping rim|内侧斜缘
near-side armrest|近侧扶手
outer body|外侧桶身
outer lip|外缘
outer shade|外灯罩
outer side edges|外侧边缘
outside|外侧
palm-rest panel|掌托面板
right armrest|右扶手
right-hand drawer front|右侧抽屉面板
round tabletop|圆桌面
shoulder-bag strap|肩包背带
side|侧面
side and front-edge housing|侧面及前沿外壳
side slats|侧板条
sides|侧板
slanted front leg|倾斜前腿
spine and cover edge|书脊及封面边缘
straps|背带
supporting leg frame|支腿框架
sweater sleeve|毛衣袖子
tabletop|桌面
top|桌面
top drawer front|最上层抽屉面板
vertical backrest slats|椅背竖条
wide rim|宽边缘
woven side wall|编织侧壁
lower drawer fronts|下方抽屉面板
indicated drawer fronts|指定抽屉面板""".splitlines()
)


def scope_zh(scope, category):
    original = scope
    s = scope.removeprefix("the ")
    prefix = ""
    if s.startswith("all "):
        prefix, s = "所有", s[4:]
    elif s.startswith("both "):
        prefix, s = "两处", s[5:]
    for word, zh in [
        ("twelve ", "十二块"),
        ("six ", "六块"),
        ("five ", "五个"),
        ("four ", "四个"),
        ("three ", "三个"),
    ]:
        if s not in BASE and s.startswith(word):
            prefix = ("全部" if prefix else "") + zh
            s = s[len(word) :]
            break
    visible = s.startswith("visible ")
    if visible:
        s = s[8:]
    if s not in BASE:
        raise ValueError(original)
    value = BASE[s]
    parent, part = category.split(":")
    if s in {"handle", "handles", "exposed handle", "long handle"}:
        noun = {
            "knife": "刀柄",
            "spoon": "勺柄",
            "cup": "杯把",
            "mug": "杯把",
            "hammer": "锤柄",
            "screwdriver": "手柄",
            "basket": "提手",
            "handbag": "提带",
            "plastic_bag": "提手",
            "pliers": "手柄",
        }.get(parent, "把手")
        value = ("裸露的" if s == "exposed handle" else "长" if s == "long handle" else "") + noun
    if s in {"body", "outside body", "rounded body"}:
        noun = {
            "glass_(drink_container)": "杯身",
            "cup": "杯身",
            "bowl": "碗身",
            "vase": "瓶身",
            "bottle": "瓶身",
            "handbag": "包身",
            "can": "罐身",
            "trash_can": "桶身",
            "soap": "瓶身",
            "lamp": "灯体",
        }.get(parent, "主体")
        value = ("外侧" if s == "outside body" else "圆腹" if s == "rounded body" else "") + noun
    if s in {"rim", "thin rim", "thin visible rim"}:
        noun = {
            "glass_(drink_container)": "杯口",
            "cup": "杯口",
            "mug": "杯口",
            "bowl": "碗口",
            "bucket": "桶口",
            "trash_can": "桶口",
            "basket": "篮口",
        }.get(parent, "边缘")
        value = ("细" if s != "rim" else "") + noun
    if s == "blades" and parent in {"scissors", "knife"}:
        value = "刀刃"
    if prefix == "两处":
        classifier = (
            "条"
            if any(k in s for k in ("legs", "handles"))
            else "块"
            if "fronts" in s or "panels" in s
            else "扇"
            if s == "doors"
            else "只"
            if "sleeves" in s
            else "片"
            if s in {"blades", "wings"}
            else "个"
        )
        prefix = "两" + classifier
    if prefix.endswith("个"):
        classifier = (
            "扇"
            if s == "doors"
            else "块"
            if "fronts" in s
            else "片"
            if s in {"blades", "wings"}
            else "个"
        )
        prefix = prefix[:-1] + classifier
    return prefix + ("可见的" if visible else "") + value

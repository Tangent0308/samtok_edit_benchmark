"""Chinese part types for the no-ref variant; never add hidden instance positions."""

SCOPES = dict(
    line.split("|")
    for line in """T-shirt|T恤
backpack|双肩包
backpack body|双肩包包身
backpack strap|双肩包肩带
backpack straps|双肩包肩带
backrest and uprights|靠背及竖直支柱
bag|包
bag body|包身
bag handle|包提手
basket|篮子
basket rim|篮口边缘
bauble|装饰球
beanie|针织无檐帽
bench|长凳
beret|贝雷帽
bicycle frame|自行车车架
bicycle handlebar|自行车车把
blouse|女式衬衫
boot|靴子
bottle|瓶子
bottoms|下装
bowl|碗
bowl wall|碗壁
cap|帽子
cat|猫
chair|椅子
chair back|椅背
chair backrest|椅子靠背
chair frame|椅子框架
chair rail|椅子横条
chair seat|椅子座面
chair shell|座椅壳
coat|外套
collar|衣领
container|容器
crank|曲柄
crown|冠饰
decoration|装饰物
dish|盘子
door handle|门把手
dress|连衣裙
excavator arm|挖掘机支臂
fender|挡泥板
figurine|摆件
figurine body|摆件身体
fruit bag|水果袋
garment|衣物
glass|玻璃杯
glove|手套
handbag|手提包
handle|把手
hard hat|安全帽
hat|帽子
hat body|帽身
headscarf|头巾
helmet|头盔
helmet shell|头盔外壳
hood|兜帽
horn|号角
jacket|夹克
jersey|运动衫
jug body|壶身
lamp stand|灯架
leggings|打底裤
life jacket|救生衣
light bulb|灯泡
longyi|隆基裙
meal tray|餐盘
motorcycle fender|摩托车挡泥板
package|包装
packet|小包装
palm|棕榈树
pannier|侧挂包
parcel|包裹
parcel wrapping|包裹外包装
phone|手机
pocket|口袋
pole|杆
reel|卷线器
rein|缰带
rivet|铆钉
robe|长袍
rod handle|钓竿手柄
sack|袋子
saddle|鞍座
saddle pad|鞍垫
scarf|围巾
scoop|勺子
seat|座面
shaft|杆身
shirt|衬衫
shirt collar|衬衫衣领
shirt section|衬衫局部
shirt sections|衬衫可见部分
shoe|鞋子
shoe sole|鞋底
shopping bag|购物袋
shorts|短裤
skewer|签子
skirt|裙子
sleeve|衣袖
sock|袜子
steering wheel|方向盘
steering wheel rim|方向盘轮缘
stool|凳子
strap|带子
strap segment|带子局部
streetlamp|路灯
suitcase|行李箱
suitcase handle|行李箱提手
tabi sock|分趾袜
tail fin|垂直尾翼
tie|领带
top|上衣
traffic light|交通信号灯
tray|托盘
tray rim|托盘边框
tray surface|托盘表面
tripod|三脚架
trouser leg|裤腿
trousers|长裤
umbrella|伞
umbrella canopy|伞面
vase|花瓶
vest|背心
visor|面罩
wall lantern|壁灯
wheel panel|车轮面板
wok|炒锅
workwear|工作服
woven cover|编织盖""".splitlines()
)

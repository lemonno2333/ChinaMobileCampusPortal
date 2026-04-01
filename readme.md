# 移动校园网自动认证脚本

![image-20260401202113896](img\PixPin_2026-04-01_20-21-11.png)

仅支持如图所示的认证网页。

## 食用方法

脚本支持PC端和路由器端使用，目前仅在Windows端测试成功

## PC端（以Windows为例）

首先你需要确定电脑中安装了python，且已经添加到环境变量中。

首先请将仓库克隆到本地

随后安装Pillow

```python
pip install pillow
```

打开login.py文件，编辑以下内容（内容需填写至引号内）

```python
USERNAME = ""
PASSWORD = ""
PORTAL = ""
PARAMS = {
    "brasip": "183.221.85.251",
    "braslogoutip": "",
    "area": "union",
    "wlanuserip": "null",
    "redirectUrl": "example/sccmcceducookie/cnunion",
    "domain": "@cmccgxsd",
    "wlanparameter": "null"
}
CAPTCHA_IMG = "captcha.png"
SOLVE_SCRIPT = "solve_captcha-PC.py"
TEMPLATE_DIR = "templates"
```

其中 USERNAME 填写你的校园网账号

PASSWORD 填写你的校园网密码

PORTAL 填写校园网认证网址，如：http://xxx.xxx.xxx.xxx/portalserver

PARAMS 的内容需要根据实际情况填写，首先请打开你的校园网认证页面，用F12或者其他方法唤起开发者工具，并且点击”网络“菜单，并且开启录制网络日志(如图)

![image-20260401203514821](img\PixPin_2026-04-01_20-35-00.png)

随后正常登录一次校园网，找到发送的请求（如图）
![image-20260401203701954](img\PixPin_2026-04-01_20-36-54.png)

请求网址大致如下

```

http://xxx.xxx.xxx.xxx:xxxx/portalserver/user/unionautologin.do?brasip=xxxx&braslogoutip=&area=union&wlanuserip=null&redirectUrl=example/sccmcceducookie/cnunion&domain=@cmccgxsd&wlanparameter=null
```

其中校园网认证网址之后的，就是你需要添加进PARAMS 的内容，比如此处，认证网址为
http://xxx.xxx.xxx.xxx:xxxx/portalserver/user/unionautologin.do?
则需要添加的内容为

```python
    "brasip": "xxxx",
    "braslogoutip": "",
    "area": "union",
    "wlanuserip": "null",
    "redirectUrl": "example/sccmcceducookie/cnunion",
    "domain": "@cmccgxsd",
    "wlanparameter": "null"
```

如果你的校园网认证网址不为http://xxx.xxx.xxx.xxx:xxxx/portalserver/user/unionautologin.do?开头的话，则需将login.py中其他地方的网址一起修改。

例如你的网址是http://xxx.xxx.xxx.xxx:xxxx/portalserver/example/unionexample.do，则login_once的

```
session.get(f"{PORTAL}/user/unionautologin.do", params=PARAMS)
```

需要修改成

```
session.get(f"{PORTAL}/example/unionexample.do", params=PARAMS)
```

而验证的获取逻辑

```
img_resp = session.get(f"{PORTAL}/user/randomimage")
```

也可能需要同步更改成

```
img_resp = session.get(f"{PORTAL}/example/randomimage")
```

具体网址请通过F12或抓包进行确认。

修改完成后，执行

```
python login.py
```

即可自动进行登录。
![image-20260401204617087](img\PixPin_2026-04-01_20-46-14.png)

## 路由器端（以OpenWRT为例）

首先使用ssh连接至路由器，并安装python和libjpeg-turbo-utils

```
apk add libjpeg-turbo-utils
apk add python
```

或者使用opkg进行安装

```
opkg install python
opkg install libjpeg-turbo-utils
```

随后将仓库克隆下来，保留campus_login.sh，solve_captcha-Router.py和templates文件夹保留，其余文件可根据路由器内存大小自行决定是否保留。

打开campus_login.sh文件，编辑以下内容（内容需填写至引号内）

```
USERNAME=""
PASSWORD=""
PORTAL=""
PARAMS=""
COOKIE="/tmp/campus_cookie.txt"
CAPTCHA_IMG="/tmp/captcha.jpg"
SOLVE_SCRIPT="/usr/bin/Xiaoyuanwang/solve_captcha-Router.py"
MAX_RETRIES=5
CHECK_HOST="223.5.5.5"
```

USERNAME为你的校园网账号

PASSWORD为你的校园网密码

PORTAL为你的校园网认证网址

PARAMS 的内容与PC端的大致相同，此处不做赘述，唯一需要注意的是

```
http://xxx.xxx.xxx.xxx:xxxx/portalserver/user/unionautologin.do?brasip=xxxx&braslogoutip=&area=union&wlanuserip=null&redirectUrl=example/sccmcceducookie/cnunion&domain=@cmccgxsd&wlanparameter=null
```

在此处只需填写为

```
brasip=xxxx&braslogoutip=&area=union&wlanuserip=null&redirectUrl=example/sccmcceducookie/cnunion&domain=@cmccgxsd&wlanparameter=null
```

即

```
PARAMS="brasip=xxxx&braslogoutip=&area=union&wlanuserip=null&redirectUrl=example/sccmcceducookie/cnunion&domain=@cmccgxsd&wlanparameter=null"
```

MAX_RETRIES为最大重试次数，可按需修改

CHECK_HOST为测试连通性的网址，此处为阿里DNS

**如果你不按照此教程的目录存放脚本，则需将SOLVE_SCRIPT手动指向solve_captcha-Router.py的所在目录**

编辑完成后，手动将campus_login.sh，solve_captcha-Router.py和templates文件夹上传到路由器的/usr/bin/Xiaoyuanwang/目录下（也可存放至其他目录，但请手动修改脚本中的相关内容）

随后在ssh内执行

```
chmod +x /usr/bin/Xiaoyuanwang/campus_login.sh
```

设置权限。

随后要登录时，ssh执行

```
sh /usr/bin/Xiaoyuanwang/campus_login.sh
```

即可执行脚本

# 可能遇到的问题

## OpenWRT

1. 如果运行脚本时提示

```
root@OWRT:~# sh /usr/bin/Xiaoyuanwang/campus_login.sh
: not foundaoyuanwang/campus_login.sh: line 4: 
: not foundaoyuanwang/campus_login.sh: line 14: 
[19:40:07] 
: not foundaoyuanwang/campus_login.sh: line 17: }
: not foundaoyuanwang/campus_login.sh: line 18: 
/usr/bin/Xiaoyuanwang/campus_login.sh: line 21: redir error
root@OWRT:~#
```

则需要处理以下换行符，ssh执行

```
sed -i 's/\r//' /usr/bin/Xiaoyuanwang/campus_login.sh
```

随后再次运行即可。



2. 如果需要设置开机自启，可以在OpenWRT管理页面中的 系统>启动项>本地启动脚本 中，添加下列指令即可

   ```
   sleep 120 && sh /usr/bin/Xiaoyuanwang/campus_login.sh > /dev/null 2>&1 &
   ```

此处默认开机后2分钟后再进行认证，如需修改，请手动将sleep 120处的120修改为相应的秒数。



3. 如果脚本运行时间过长或卡死，则为路由器性能问题，请酌情考虑是否要在路由器上使用此脚本

   

4. 如果遇到其他问题，复制相关报错到Ai进行解答，或许更方便

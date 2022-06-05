from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from datetime import timedelta
import datetime
import mysql.connector
import re
import MySQLdb.cursors
import flask
import urllib.request
import urllib.parse
import urllib.parse as parse
import json
import base64
import socketio
from werkzeug.utils import secure_filename
import os
from requests_oauthlib import OAuth1Session
from flask_socketio import SocketIO, join_room, leave_room, emit
import smtplib
from email.mime.text import MIMEText

from GMF import get_data, preprocess_dataset, \
    SampleGenerator, setting, GMF, check_1, train, minus1, check_2, model, test_

app = Flask(__name__)

# セッション設定
app.secret_key = 'user_id'
app.config['SECRET_KEY'] = 'aaalllaa' # これが暗号化／復号のための鍵になる
app.config['SESSION_TYPE'] = 'filesystem'

# ファイルアップロード設定
UPLOAD_FOLDER = './static/images/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# SocketIO設定
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)


# socketio.init_app(app, cors_allowed_origins="*")

# メール設定
def send_mail(email, message):
    smtp_host = 'smtp.gmail.com'
    smtp_port = 465
    username = ''
    password = ''
    smtp = smtplib.SMTP_SSL(smtp_host, smtp_port)
    smtp.login(username, password)

    msg = MIMEText(message, 'html')
    msg["Subject"] = "タイトル"
    msg["To"] = email
    msg["From"] = "SNS"
    smtp.send_message(msg)

    smtp.quit()


# データベースを操作する関数
def cdb():
    db = mysql.connector.connect(
        user='root',
        password='password',
        host='db',
        database='app'
    )
    return db


# user_idからユーザ名を取得する関数
def find_user(user_id):
    db = cdb()
    cursor = db.cursor(buffered=True)
    cursor.execute("SELECT nickname FROM Profiles WHERE id = %s", (user_id,))
    name = cursor.fetchall()[0][0]
    return name


# Mutual friend関数
def mutual_friend():
    db = cdb()
    follow_id = db.cursor(buffered=True)
    follow_id.execute("SELECT followed_id from Follows where follow_id = %s", (session['user_id'],))
    # ログインユーザーをフォローしている人
    followed_id = db.cursor(buffered=True)
    followed_id.execute("SELECT follow_id from Follows where followed_id = %s", (session['user_id'],))

    follow_f = follow_id.fetchall()
    followed_f = followed_id.fetchall()

    follow_li = [i[0] for i in follow_f]

    followed_li = [i[0] for i in followed_f]
    # 共通する部分をリスト化
    Mutuals = tuple(set(follow_li) & set(followed_li))

    Mutual_friends = []

    for Mutual in Mutuals:
        list_friends = db.cursor(buffered=True)
        list_friends.execute("SELECT icon, nickname, id from Profiles where id = %s", (Mutual,))
        m = list_friends.fetchall()
        Mutual_friends.append(m)

    return Mutuals, Mutual_friends, followed_li


@app.route("/")
def main():
    db = cdb()
    cursor = db.cursor(buffered=True)
    cursor.execute("SELECT * FROM Profiles")

    games = db.cursor(buffered=True)
    games.execute("SELECT * FROM Games")

    return render_template("index.html", users=cursor.fetchall(), games=games.fetchall())


@app.route('/login/', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'nickname' in request.form and 'password' in request.form:
        nickname = request.form['nickname']
        password = request.form['password']
        cnx = cdb()
        cursor = cnx.cursor(buffered=True)
        cursor.execute('SELECT * FROM Profiles WHERE nickname=%s AND password=%s', (nickname, password))
        account = cursor.fetchone()

        if account:
            session.permanent = True
            app.permanent_session_lifetime = timedelta(minutes=3)
            session.modified = True
            user = request.form['nickname']
            session['user'] = user
            session['loggedin'] = True
            session['user_id'] = account[0]
            return redirect("/top")

        else:
            msg = 'incorrect username or password'

        return render_template("login.html", msg=msg)

    else:
        return render_template('login.html')


@app.route('/main')
def main1():
    cnx = cdb()
    cursor = cnx.cursor(buffered=True)
    cursor.execute("SELECT * FROM Profiles WHERE id = %s", (session['user_id'],))
    account = cursor.fetchone()

    return render_template('top.html', session=session['user'], session_id=session['user_id'], account=account,
                           log=session['loggedin'], user=session['user'])


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def register_interface(type, words, limit_words):
    if type == "nickname":
        if len(words) < limit_words:
            return False
        else:
            return True
    elif type == "password":
        if len(words) < limit_words:
            return False
    is_match = [0, 0, 0]  # 大文字、小文字、数字なら各要素に1をセット
    for c in words:
        if re.match(r'[A-Z]', c):
            is_match[0] = 1
        elif re.match(r'[a-z]', c):
            is_match[1] = 1
        elif re.match(r'[0-9]', c):
            is_match[2] = 1
        # もし「上記のみで構成される」という制約をつけたいなら、以下のコメント部分を生かす
        else:
            return False  # それ以外はだめ
    return sum(is_match) == 3  # すべてを含む


@app.route('/register2', methods=['GET', 'POST'])
def register2():
    msg = ''
    if request.method == 'POST' and 'nickname' in request.form \
            and 'password' in request.form and 'email' in request.form:
        nickname = request.form['nickname']
        password = request.form['password']
        email = request.form['email']

        if (nickname is None) or (password is None) or (email is None):
            pass
        else:
            if register_interface("password", password, 8) == False:
                msg = 'A-Z, a-z, 0-9をそれぞれ１字以上を含め、合計8文字以上で入力してください'
                return render_template('register2.html', msg=msg)
            if register_interface("nickname", nickname, 1) == False:
                msg = 'ニックネームは1文字以上で入力してください'
                return render_template('register2.html', msg=msg)

        db = cdb()
        cursor = db.cursor(buffered=True)
        cursor.execute('SELECT * FROM Profiles WHERE nickname=%s AND password=%s',
                       (nickname, password))
        account = cursor.fetchone()

        if account:
            return render_template('login.html')

        else:
            cursor = db.cursor(buffered=True)
            cursor.execute("INSERT INTO Profiles (nickname, password, email) values (%s, %s, %s)",
                           (nickname, password, email,))
            db.commit()

            cursor = db.cursor(buffered=True)
            cursor.execute('SELECT * FROM Profiles WHERE nickname=%s AND password=%s', (nickname, password))
            account_new = cursor.fetchone()

            session.permanent = True
            app.permanent_session_lifetime = timedelta(minutes=3)
            session.modified = True
            session['user'] = nickname
            session['loggedin'] = True
            session['user_id'] = account_new[0]

            return render_template('top.html')

    else:
        return render_template('register2.html')


@app.route('/google')
def google():
    return flask.redirect('https://accounts.google.com/o/oauth2/auth?{}'.format(urllib.parse.urlencode({
        'client_id': client_id,
        'scope': 'profile email',
        'redirect_uri': redirect_uri,
        'state': state,
        'openid.realm': 'http://localhost:5000',
        'response_type': 'code'
    })))


@app.route('/login/check')
def check():
    print(flask.request.args.get('state'))
    dat = urllib.request.urlopen('https://www.googleapis.com/oauth2/v4/token', urllib.parse.urlencode({
        'code': flask.request.args.get('code'),
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }).encode('ascii')).read()

    dat = json.loads(dat.decode('ascii'))

    id_token = dat['id_token'].split('.')[1]  # 署名はとりあえず無視する
    id_token = id_token + '=' * (4 - len(id_token) // 4)  # パディングが足りなかったりするっぽいので補う
    id_token = base64.b64decode(id_token)
    id_token = json.loads(id_token.decode('ascii'))

    nick_name = id_token['name']
    email = id_token['email']
    password = 'password'

    cnx = cdb()
    cursor = cnx.cursor(buffered=True)
    cursor.execute('SELECT * FROM Profiles WHERE nickname=%s AND email=%s', (nick_name, email,))
    account = cursor.fetchone()

    if account:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=3)
        session.modified = True
        session['user'] = nick_name
        session['loggedin'] = True
        session['user_id'] = account[0]

        return render_template('top.html')

    else:
        cnx = cdb()
        cursor = cnx.cursor(buffered=True)
        cursor.execute("INSERT INTO Profiles (nickname, password, email) values (%s, %s, %s)",
                       (nick_name, password, email,))
        cnx.commit()

        cursor = cnx.cursor(buffered=True)
        cursor.execute('SELECT * FROM Profiles WHERE nickname=%s AND password=%s', (nick_name, password))
        account_new = cursor.fetchone()

        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=3)
        session.modified = True
        session['user'] = nick_name
        session['loggedin'] = True
        session['user_id'] = account_new[0]

        return render_template('top.html')


@app.route("/twitter")
def twitter():
    # 1.リクエストトークンを取得する。
    # (Step 1: Obtaining a request token:https://developer.twitter.com/en/docs/authentication/guides/log-in-with-twitter)
    twitter = OAuth1Session(api_key, api_secret)
    oauth_callback = request.args.get('oauth_callback')
    res = twitter.post(request_token_endpoint, params={
        'oauth_callback': oauth_callback})
    request_token = dict(parse.parse_qsl(res.content.decode("utf-8")))
    oauth_token = request_token['oauth_token']

    # 2.リクエストトークンを指定してTwitterへ認可リクエスト(Authorization Request)を行う。
    # (Step 2: Redirecting the user:https://developer.twitter.com/en/docs/authentication/guides/log-in-with-twitter#tab2)
    return redirect(authorization_endpoint + '?{}'.format(parse.urlencode({
        'oauth_token': oauth_token
    })))


@app.route("/callback_twitter")
def callback():
    # 3.ユーザー認証/同意を行い、認可レスポンスを受け取る。
    oauth_verifier = request.args.get('oauth_verifier')
    oauth_token = request.args.get('oauth_token')

    # 4.認可レスポンスを使ってトークンリクエストを行う。
    # (Step 3: Converting the request token to an access token:https://developer.twitter.com/en/docs/authentication/guides/log-in-with-twitter#tab3)
    twitter = OAuth1Session(
        api_key,
        api_secret,
        oauth_token
    )

    res = twitter.post(
        token_endpoint,
        params={'oauth_verifier': oauth_verifier}
    )

    access_token = dict(parse.parse_qsl(res.content.decode("utf-8")))
    # info = jsonify(access_token)
    nick_name = str('initial')
    # nick_name = []
    for i in access_token.values():
        nick_name = i
    password = nick_name
    email = nick_name

    cnx = cdb()
    cursor = cnx.cursor(buffered=True)
    cursor.execute('SELECT * FROM Profiles WHERE nickname=%s AND email=%s', (nick_name, email))
    account = cursor.fetchone()

    if account:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=3)
        session.modified = True
        session['user'] = nick_name
        session['loggedin'] = True
        session['user_id'] = account[0]
        return render_template('top.html')

    else:
        cnx = cdb()
        cursor = cnx.cursor(buffered=True)
        cursor.execute("INSERT INTO Profiles (nickname, password, email) values (%s, %s, %s)",
                       (nick_name, password, email,))
        cnx.commit()

        cursor = cnx.cursor(buffered=True)
        cursor.execute('SELECT * FROM Profiles WHERE nickname=%s AND email=%s', (nick_name, email))
        account_new = cursor.fetchone()
        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=3)
        session.modified = True
        session['user'] = nick_name
        session['loggedin'] = True
        session['user_id'] = account_new[0]
        return render_template('top.html')


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if 'loggedin' in session:
        db = cdb()
        if request.method == "POST":

            if request.form.get("follow") == "フォロー":
                user_follow = db.cursor(buffered=True)
                user_follow.execute("INSERT INTO Follows (follow_id, followed_id) VALUES (%s, %s)",
                                    (session['user_id'], session['profile_id']))
                db.commit()
                follow = db.cursor(buffered=True)
                follow.execute("SELECT nickname FROM Profiles WHERE id = %s", (session['user_id'],))
                follow_name = follow.fetchall()[0][0]
                followed = db.cursor(buffered=True)
                followed.execute("SELECT nickname, email FROM Profiles WHERE id = %s", (session['profile_id'],))
                followed_pro = followed.fetchall()[0]
                followed_name = followed_pro[0]
                followed_mail = followed_pro[1]

                # send_mail(followed_mail, f"{followed_name}さん。あなたは{follow_name}さんにフォローされました")
            elif request.form.get("unfollow") == "フォローをやめる":
                user_unfollow = db.cursor(buffered=True)
                user_unfollow.execute("DELETE FROM Follows WHERE follow_id = %s AND followed_id = %s",
                                      (session['user_id'], session['profile_id']))
                db.commit()

            elif request.form.get("talk") != None:
                db = cdb()
                try:
                    get_group = db.cursor(buffered=True)
                    get_group.execute(
                        "SELECT id FROM Groups flag_talk = %s AND id = (SELECT group_id FROM Members WHERE member_id IN (%s, %s) GROUP BY group_id HAVING COUNT(group_id) > 1)",
                        (0, session['user_id'], request.form.get('talk_id')))

                    session['room_id'] = get_group.fetchall()[0][0]
                except:
                    session['room_id'] = request.form.get("talk_id")
                    set_name = find_user(session['user_id']) + find_user(session['room_id']) + "のトーク"

                    set_group = db.cursor(buffered=True)
                    set_group.execute("INSERT INTO Groups (group_name) VALUES (%s)", (set_name,))
                    db.commit()

                    group_id = db.cursor(buffered=True)
                    group_id.execute("SELECT id FROM Groups WHERE group_name = %s", (set_name,))
                    group = group_id.fetchall()[0][0]

                    into_group_user = db.cursor(buffered=True)
                    into_group_user.execute("INSERT INTO Members (member_id, group_id, flag_join) VALUES (%s, %s, %s)",
                                            (session['user_id'], group, 1))
                    db.commit()

                    into_group_follower = db.cursor(buffered=True)
                    into_group_follower.execute(
                        "INSERT INTO Members (member_id, group_id, flag_join) VALUES (%s, %s, %s)",
                        (request.form.get('talk_id'), group, 1))
                    db.commit()
                    session['room_id'] = group

                get_group_name = db.cursor(buffered=True)
                get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
                session['room_name'] = get_group_name.fetchall()[0][0]
                return redirect("/talk")

            return redirect("/profile")



        else:
            cursor = db.cursor(buffered=True)
            cursor.execute("SELECT * FROM Profiles WHERE id=%s", (session['profile_id'],))
            user_profile = cursor.fetchall()[0]

            isFollow = db.cursor(buffered=True)
            isFollow.execute("SELECT COUNT(*) FROM Follows WHERE follow_id = %s AND followed_id = %s",
                             (session['user_id'], session['profile_id']))
            isFollow2 = isFollow.fetchall()[0][0]

            game_list = db.cursor(buffered=True)
            game_list.execute("SELECT game_id, game_level, game_order FROM Games WHERE user_id = %s",
                              (session['profile_id'],))
            games = game_list.fetchall()

            try:
                star1 = games[0][1]
            except:
                star1 = 0
            try:
                star2 = games[1][1]
            except:
                star2 = 0
            try:
                star3 = games[2][1]
            except:
                star3 = 0

            try:
                game1 = db.cursor(buffered=True)
                game1.execute("SELECT game_name FROM Game_names WHERE id = %s", (games[0][0],))
                game_name1 = game1.fetchall()[0][0]
            except:
                game_name1 = "ゲームが選択されていません"

            try:
                game2 = db.cursor(buffered=True)
                game2.execute("SELECT game_name FROM Game_names WHERE id = %s", (games[1][0],))
                game_name2 = game2.fetchall()[0][0]
            except:
                game_name2 = "ゲームが選択されていません"

            try:
                game3 = db.cursor(buffered=True)
                game3.execute("SELECT game_name FROM Game_names WHERE id = %s", (games[2][0],))
                game_name3 = game3.fetchall()[0][0]
            except:
                game_name3 = "ゲームが選択されていません"

            mutual_follow_cursor = db.cursor(buffered=True)
            mutual_follow_cursor.execute(
                "SELECT COUNT(*) FROM Follows WHERE followed_id = %s AND follow_id = %s AND follow_id IN (SELECT followed_id FROM Follows WHERE follow_id = %s AND followed_id = %s)",
                (session['user_id'], session['profile_id'], session['user_id'], session['profile_id']))
            is_mutual_follow = mutual_follow_cursor.fetchall()[0][0]

            follow = db.cursor(buffered=True)
            follow.execute("SELECT COUNT(*) FROM Follows WHERE follow_id = %s", (session['profile_id'],))
            follow_count = follow.fetchall()[0][0]

            followed = db.cursor(buffered=True)
            followed.execute("SELECT COUNT(*) FROM Follows WHERE followed_id = %s", (session['profile_id'],))
            followed_count = followed.fetchall()[0][0]

            modal_follow = db.cursor(buffered=True)
            modal_follow.execute("SELECT followed_id FROM Follows WHERE follow_id = %s", (session['profile_id'],))
            modal_follow_list = modal_follow.fetchall()
            modal_follow_list = [i[0] for i in modal_follow_list]

            follow_list = []
            for i in modal_follow_list:
                m = db.cursor(buffered=True)
                m.execute("SELECT id, nickname, icon FROM Profiles WHERE id = %s", (i,))
                n = m.fetchall()
                n = list(n)
                follow_list.append(n)

            modal_followed = db.cursor(buffered=True)
            modal_followed.execute("SELECT follow_id FROM Follows WHERE followed_id = %s", (session['profile_id'],))
            modal_followed_list = modal_followed.fetchall()
            modal_followed_list = [i[0] for i in modal_followed_list]

            followed_list = []
            for i in modal_followed_list:
                m = db.cursor(buffered=True)
                m.execute("SELECT id, nickname, icon FROM Profiles WHERE id = %s", (i,))
                n = m.fetchall()
                n = list(n)
                followed_list.append(n)

        return render_template("profile.html", user_profile=user_profile,
                               star1=star1, star2=star2, star3=star3, game_name1=game_name1, game_name2=game_name2,
                               game_name3=game_name3, follow_count=follow_count, followed_count=followed_count,
                               isFollow2=isFollow2, is_mutual_follow=is_mutual_follow, session=session,
                               modal_follow_list=follow_list, modal_followed_list=followed_list)

    return redirect(url_for('login'))


@app.route("/edit", methods=["GET", "POST"])
def edit():
    if 'loggedin' in session:
      session['user_id'] = session['user_id']
      db = cdb()

      if request.method == "POST":
        # 画像変更
        try:
          img_file = request.files['up_file']
          filename = secure_filename(img_file.filename)
          img_url = os.path.join(app.config['UPLOAD_FOLDER'], filename)
          img_file.save(img_url)

          cursor = db.cursor(buffered=True)
          cursor.execute("UPDATE Profiles SET icon = %s WHERE id = %s", (UPLOAD_FOLDER + filename, session['user_id']))
          db.commit()
        except:
          pass

        # ゲーム変更
        if request.form.get("game1"):
          edit_game1 = db.cursor(buffered=True)
          edit_game1.execute("SELECT id FROM Game_names WHERE game_name = %s", (request.form.get("game1"),))
          game_name_1 = edit_game1.fetchall()[0][0]
          
          set_game1 = db.cursor(buffered=True)
          contain_game1 = db.cursor(buffered=True)
          contain_game1.execute("SELECT * FROM Games WHERE user_id = %s AND game_order = %s", (session['user_id'], 1))
          is_contain1 = contain_game1.fetchall()
          if is_contain1:
            set_game1.execute("UPDATE Games SET game_id = %s WHERE user_id = %s AND game_order = %s", (game_name_1 ,session['user_id'], 1))
          else:
            set_game1.execute("INSERT INTO Games (user_id, game_id, game_level, game_order) VALUES (%s, %s, %s, %s)", (session['user_id'], game_name_1, 1, 1))
          db.commit()

        if request.form.get("skill1"):
          try:
            star1 = db.cursor(buffered=True)
            star1.execute("UPDATE Games SET game_level = %s WHERE user_id = %s AND game_order = %s", (request.form.get("skill1"), session['user_id'], 1))
            db.commit()
          except:
            pass

        if request.form.get("game2"):
          edit_game2 = db.cursor(buffered=True)
          edit_game2.execute("SELECT id FROM Game_names WHERE game_name = %s", (request.form.get("game2"),))
          game_name_2 = edit_game2.fetchall()[0][0]
          
          set_game2 = db.cursor(buffered=True)
          contain_game2 = db.cursor(buffered=True)
          contain_game2.execute("SELECT * FROM Games WHERE user_id = %s AND game_order = %s", (session['user_id'], 2))
          is_contain2 = contain_game2.fetchall()
          if is_contain2:
            set_game2.execute("UPDATE Games SET game_id = %s WHERE user_id = %s AND game_order = %s", (game_name_2 ,session['user_id'], 2))
          else:
            set_game2.execute("INSERT INTO Games (user_id, game_id, game_level, game_order) VALUES (%s, %s, %s, %s)", (session['user_id'], game_name_2, 1, 2))
          db.commit()

        if request.form.get("skill2"):
          try:
            star2 = db.cursor(buffered=True)
            star2.execute("UPDATE Games SET game_level = %s WHERE user_id = %s AND game_order = %s", (request.form.get("skill2"), session['user_id'], 2))
            db.commit()
          except:
            pass

        if request.form.get("game3"):
          edit_game3 = db.cursor(buffered=True)
          edit_game3.execute("SELECT id FROM Game_names WHERE game_name = %s", (request.form.get("game3"),))
          game_name_3 = edit_game3.fetchall()[0][0]

          set_game3 = db.cursor(buffered=True)
          contain_game3 = db.cursor(buffered=True)
          contain_game3.execute("SELECT * FROM Games WHERE user_id = %s AND game_order = %s", (session['user_id'], 3))
          is_contain3 = contain_game3.fetchall()
          if is_contain3:
            set_game3.execute("UPDATE Games SET game_id = %s WHERE user_id = %s AND game_order = %s", (game_name_3 ,session['user_id'], 3))
          else:
            set_game3.execute("INSERT INTO Games (user_id, game_id, game_level, game_order) VALUES (%s, %s, %s, %s)", (session['user_id'], game_name_3, 1, 3))
          db.commit()    

        if request.form.get("skill3"):
          try:
            star3 = db.cursor(buffered=True)
            star3.execute("UPDATE Games SET game_level = %s WHERE user_id = %s AND game_order = %s", (request.form.get("skill3"), session['user_id'], 3))
            db.commit()
          except:
            pass

        # その他変更
        set_prof = db.cursor(buffered=True)
        set_prof.execute("UPDATE Profiles SET nickname = %s, password = %s, email = %s, comment = %s WHERE id = %s", (request.form.get("nickname"), request.form.get("password"), request.form.get("email"), request.form.get("comment"), session['user_id']))
        db.commit()
        return redirect("/edit")
      else:
        session['user_id'] = session['user_id']
        db = cdb()

        if request.method == "POST":
            # 画像変更
            try:
                img_file = request.files['up_file']
                filename = secure_filename(img_file.filename)
                img_url = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                img_file.save(img_url)

                cursor = db.cursor(buffered=True)
                cursor.execute("UPDATE Profiles SET icon = %s WHERE id = %s",
                               (UPLOAD_FOLDER + filename, session['user_id']))
                db.commit()
            except:
                pass

            # ゲーム変更
            if request.form.get("game1"):
                edit_game1 = db.cursor(buffered=True)
                edit_game1.execute("SELECT id FROM Game_names WHERE game_name = %s", (request.form.get("game1"),))
                game_name_1 = edit_game1.fetchall()[0][0]

                set_game1 = db.cursor(buffered=True)
                contain_game1 = db.cursor(buffered=True)
                contain_game1.execute("SELECT * FROM Games WHERE user_id = %s AND game_order = %s",
                                      (session['user_id'], 1))
                is_contain1 = contain_game1.fetchall()
                if is_contain1:
                    set_game1.execute("UPDATE Games SET game_id = %s WHERE user_id = %s AND game_order = %s",
                                      (game_name_1, session['user_id'], 1))
                else:
                    set_game1.execute(
                        "INSERT INTO Games (user_id, game_id, game_level, game_order) VALUES (%s, %s, %s, %s)",
                        (session['user_id'], game_name_1, 1, 1))
                db.commit()

            if request.form.get("skill1"):
                try:
                    star1 = db.cursor(buffered=True)
                    star1.execute("UPDATE Games SET game_level = %s WHERE user_id = %s AND game_order = %s",
                                  (request.form.get("skill1"), session['user_id'], 1))
                    db.commit()
                except:
                    pass

            if request.form.get("game2"):
                edit_game2 = db.cursor(buffered=True)
                edit_game2.execute("SELECT id FROM Game_names WHERE game_name = %s", (request.form.get("game2"),))
                game_name_2 = edit_game2.fetchall()[0][0]

                set_game2 = db.cursor(buffered=True)
                contain_game2 = db.cursor(buffered=True)
                contain_game2.execute("SELECT * FROM Games WHERE user_id = %s AND game_order = %s",
                                      (session['user_id'], 2))
                is_contain2 = contain_game2.fetchall()
                if is_contain2:
                    set_game2.execute("UPDATE Games SET game_id = %s WHERE user_id = %s AND game_order = %s",
                                      (game_name_2, session['user_id'], 2))
                else:
                    set_game2.execute(
                        "INSERT INTO Games (user_id, game_id, game_level, game_order) VALUES (%s, %s, %s, %s)",
                        (session['user_id'], game_name_2, 1, 2))
                db.commit()

            if request.form.get("skill2"):
                try:
                    star2 = db.cursor(buffered=True)
                    star2.execute("UPDATE Games SET game_level = %s WHERE user_id = %s AND game_order = %s",
                                  (request.form.get("skill2"), session['user_id'], 2))
                    db.commit()
                except:
                    pass

            if request.form.get("game3"):
                edit_game3 = db.cursor(buffered=True)
                edit_game3.execute("SELECT id FROM Game_names WHERE game_name = %s", (request.form.get("game3"),))
                game_name_3 = edit_game3.fetchall()[0][0]

                set_game3 = db.cursor(buffered=True)
                contain_game3 = db.cursor(buffered=True)
                contain_game3.execute("SELECT * FROM Games WHERE user_id = %s AND game_order = %s",
                                      (session['user_id'], 3))
                is_contain3 = contain_game3.fetchall()
                if is_contain3:
                    set_game3.execute("UPDATE Games SET game_id = %s WHERE user_id = %s AND game_order = %s",
                                      (game_name_3, session['user_id'], 3))
                else:
                    set_game3.execute(
                        "INSERT INTO Games (user_id, game_id, game_level, game_order) VALUES (%s, %s, %s, %s)",
                        (session['user_id'], game_name_3, 1, 3))
                db.commit()

            if request.form.get("skill3"):
                try:
                    star3 = db.cursor(buffered=True)
                    star3.execute("UPDATE Games SET game_level = %s WHERE user_id = %s AND game_order = %s",
                                  (request.form.get("skill3"), session['user_id'], 3))
                    db.commit()
                except:
                    pass

                # その他変更
                set_prof = db.cursor(buffered=True)
                set_prof.execute(
                    "UPDATE Profiles SET nickname = %s, password = %s, email = %s, comment = %s WHERE id = %s", (
                    request.form.get("nickname"), request.form.get("password"), request.form.get("email"),
                    request.form.get("comment"), session['user_id']))
                db.commit()
            return redirect("/edit")
        else:

            db = cdb()
            mutual_follow = db.cursor(buffered=True)
            mutual_follow.execute(
                "SELECT COUNT(*) FROM Follows WHERE followed_id = %s AND follow_id IN (SELECT followed_id FROM Follows WHERE follow_id = %s)",
                (session['user_id'], session['user_id']))
            mutual_follow = mutual_follow.fetchall()

            user_profile = db.cursor(buffered=True)
            user_profile.execute("SELECT * FROM Profiles WHERE id = %s", (session['user_id'],))
            user_profile = user_profile.fetchall()[0]

            game_list = db.cursor(buffered=True)
            game_list.execute("SELECT game_name FROM Game_names")
            games = game_list.fetchall()

            game_all = db.cursor(buffered=True)
            game_all.execute("SELECT * FROM Games WHERE user_id = %s", (session['user_id'],))
            gameaaa = game_all.fetchall()

            follow = db.cursor(buffered=True)
            follow.execute(
                "SELECT nickname FROM Profiles WHERE id IN (SELECT followed_id FROM Follows WHERE follow_id = %s)",
                (session['user_id'],))
            follow_id_list = follow.fetchall()

            followed = db.cursor(buffered=True)
            followed.execute(
                "SELECT nickname FROM Profiles WHERE id IN (SELECT follow_id FROM Follows WHERE followed_id = %s)",
                (session['user_id'],))
            followed_id_list = followed.fetchall()

            return render_template("edit.html", games=games, user_profile=user_profile, gameaaa=gameaaa,
                                   follow_id_list=follow_id_list, followed_id_list=followed_id_list)
    else:
        return redirect(url_for('login'))


@app.route("/talk", methods=['GET', 'POST'])
def talk():
    if 'loggedin' in session:
        if request.method == "POST":
            if request.form.get("group_talk") != None:
                session['room_id'] = request.form.get("group_id")
                db = cdb()
                get_group_name = db.cursor(buffered=True)
                get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
                session['room_name'] = get_group_name.fetchall()[0][0]

            elif request.form.get("friend_talk") != None:
                db = cdb()
                try:
                    get_group = db.cursor(buffered=True)
                    get_group.execute(
                        "SELECT id FROM Groups Where flag_group = %s AND id IN (SELECT group_id FROM Members WHERE member_id = %s AND member_id =  %s)", (0, session['user_id'], request.form.get('friend_id')))

                    session['room_id'] = get_group.fetchall()[0][0]
                except:
                    session['room_id'] = request.form.get("friend_id")
                    set_name = find_user(session['user_id']) + find_user(session['room_id'])

                    set_group = db.cursor(buffered=True)
                    set_group.execute("INSERT INTO Groups (group_name) VALUES (%s)", (set_name,))
                    db.commit()

                    group_id = db.cursor(buffered=True)
                    group_id.execute("SELECT id FROM Groups WHERE group_name = %s", (set_name,))
                    group = group_id.fetchall()[0][0]

                    into_group_user = db.cursor(buffered=True)
                    into_group_user.execute("INSERT INTO Members (member_id, group_id, flag_join) VALUES (%s, %s, %s)",
                                            (session['user_id'], group, 1))
                    db.commit()

                    into_group_follower = db.cursor(buffered=True)
                    into_group_follower.execute(
                        "INSERT INTO Members (member_id, group_id, flag_join) VALUES (%s, %s, %s)",
                        (request.form.get('friend_id'), group, 1))
                    db.commit()
                    session['room_id'] = group

                get_group_name = db.cursor(buffered=True)
                get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
                session['room_name'] = get_group_name.fetchall()[0][0]
            return redirect("/talk")
        else:
            db = cdb()
            # follow = db.cursor(buffered=True)
            # follow.execute("SELECT id, nickname, icon FROM Profiles WHERE id IN (SELECT followed_id FROM Follows WHERE follow_id = %s)", (session['user_id'], ))
            # follow_id_list = follow.fetchall()
            Mutual_talk = []
            Mutuals, Mutual_friends, followed_li = mutual_friend()

            for Mutual in Mutuals:
                list_friends = db.cursor(buffered=True)
                list_friends.execute("SELECT id, nickname, icon from Profiles where id = %s", (Mutual,))
                m = list_friends.fetchall()
                Mutual_talk.append(m)

            group = db.cursor(buffered=True)
            group.execute(
                "SELECT id, group_name FROM Groups WHERE id IN (SELECT group_id FROM Members WHERE member_id = %s AND flag_join = %s) AND flag_group = %s",
                (session['user_id'], 1, 1))
            group_list = group.fetchall()

            return render_template("talk.html", session=session, follow_id_list=Mutual_talk, group_list=group_list)

    else:
        return redirect(url_for('login'))


@socketio.on('join', namespace='/talk')
def join(message):
    room = session['room_id']
    user = find_user(session['user_id'])
    db = cdb()
    get_msg = db.cursor(buffered=True)
    get_msg.execute("SELECT message FROM Messages WHERE group_id = %s", (session['room_id'],))
    view_msg = get_msg.fetchall()

    # ------------------------------------------
    # miya
    get_sender_id = db.cursor(buffered=True)
    get_sender_id.execute("SELECT sender_id FROM Messages WHERE group_id = %s", (session['room_id'],))
    view_sender_id = get_sender_id.fetchall()

    sender_li = [i[0] for i in view_sender_id]
    sender = []

    for l in sender_li:
        list_sender = db.cursor(buffered=True)
        list_sender.execute("SELECT nickname from Profiles where id = %s", (l,))
        m = list_sender.fetchall()
        sender.append(m)
    # ------------------------------------------

    user_info = db.cursor(buffered=True)
    user_info.execute("SELECT nickname, icon FROM Profiles WHERE id = %s", (session['user_id'],))
    user = user_info.fetchall()

    join_room(room)
    emit('status', {'msg': view_msg, 'sender_id': sender, 'user': user}, room=room)


@socketio.on('text', namespace='/talk')
def text(message):
    room = session['room_id']
    user = find_user(session['user_id'])

    db = cdb()
    user_info = db.cursor(buffered=True)
    user_info.execute("SELECT nickname, icon FROM Profiles WHERE id = %s", (session['user_id'],))
    user = user_info.fetchall()

    in_message = db.cursor(buffered=True)
    in_message.execute("INSERT INTO Messages (sender_id, group_id, message) VALUES (%s, %s, %s)",
                       (session['user_id'], session['room_id'], message['msg']))
    db.commit()
    emit('message', {'msg': message['msg'], 'user': user}, room=room)


@socketio.on('left', namespace='/talk')
def left(message):
    room = session['room_id']
    leave_room(room)


@app.route('/top', methods=["GET", "POST"])
def top():
    if 'loggedin' in session:
        session['user_id'] = session['user_id']

        if request.method == "GET":
            db = cdb()

            # selectボックスで使う選択肢

            # ------------------------------------------------------
            # 相互フォローの表示
            # ------------------------------------------------------
            # ログインユーザーがフォローしている人

            Mutuals, Mutual_friends, followed_li = mutual_friend()

            game_names = db.cursor(buffered=True)
            game_names.execute("SELECT game_name from Game_names")

            # 齋藤追加-------------------------------------------------------------------------------------------------------
            list_all = list(set(Mutuals)) + list(set(followed_li))
            followed_list_only = [x for x in set(list_all) if
                                  list_all.count(x) == 1]

            # followed_list_onlyからユーザーの情報を取得-------------------------------
            followed_info = []
            for user in followed_list_only:
                list_friends = db.cursor(buffered=True)
                list_friends.execute("SELECT icon, nickname, id from Profiles where id = %s", (user,))
                m = list_friends.fetchall()
                followed_info.append(m)

            # フォローの部分はここまで------------------------------------------------------

            # グループの部分--------------------------------------------------------------
            # 通知のグループを取得
            group_not_join = db.cursor(buffered=True)
            group_not_join.execute(
                "SELECT id FROM Groups WHERE id in (SELECT group_id FROM Members WHERE member_id= %s AND flag_join= %s) AND flag_group = %s",
                (session['user_id'], 0, 1))
            group_not_join = group_not_join.fetchall()

            # gropはリストの中が()になっているからリストにする---------------------------------
            list_i = []
            for i in group_not_join:
                i = i[0]
                list_i.append(i)

            # groupで取ったidでGroupsテーブルからGroup_nameとGroup_iconを取得----------------
            group_list = []
            for i in list_i:
                id = db.cursor(buffered=True)
                id.execute(
                    "SELECT group_name, group_icon, id from Groups where id = %s", (i,))
                m = id.fetchall()
                group_list.append(m)

            # ここまで------------------------------------------------------------------------------------------------------

            """
            # 入っているグループを取得
            group_join = db.cursor(buffered=True)
            group_join.execute("SELECT group_id FROM Members WHERE member_id= %s AND "
                                "flag_join= %s", (session['user_id'], 1,))
            group_id_join = group_join.fetchall()
            # groupはリストの中が()になっているからリストにする---------------------------------
            list_i_join = []
            for i in group_id_join:
              i = i[0]
              list_i_join.append(i)
            # groupで取ったidでGroupsテーブルからGroup_nameとGroup_iconを取得----------------
            group_list_join = []
            for i in list_i_join:
              id = db.cursor(buffered=True)
              id.execute(
              "SELECT group_name, group_icon, id from Groups WHERE id = %s AND flag_group = %s", (i, 1))
              m = id.fetchall()
              group_list_join.append(m)
            """

            cursor = db.cursor(buffered=True)
            cursor.execute(
                "SELECT group_name, group_icon, id from Groups WHERE id IN (SELECT group_id FROM Members WHERE member_id= %s AND flag_join= %s) AND flag_group = %s",
                (session['user_id'], 1, 1))
            group_list_join = cursor.fetchall()

            return render_template('top.html', user_id=session['user_id'], Mutuals=Mutuals,
                                   Mutual_friends=Mutual_friends, game_names=game_names,
                                   followed_info=followed_info, group_list=group_list, group_list_join=group_list_join)

        # ポップアップ1を追加---------------------------------------------------------------------------------------------------
        if request.method == 'POST' and 'group_name' in request.form and "member" in \
                request.form and request.form.get('create_group') == "グループ作成":
            db = cdb()
            image_path = "static/images/iam.jpg"
            group_name = request.form.get('group_name')
            members = request.form.getlist("member")

            # Groupの作成 (group_nameとgroup_icon→これはデフォルト設定にしてる)
            create_group = db.cursor(buffered=True)
            create_group.execute("INSERT INTO Groups (group_name, group_icon, flag_group) "
                                 "VALUES (%s, %s, %s)", (group_name, image_path, 1))
            db.commit()

            # GroupネームからそのグループIDを取ってくる。Group_nameが被った場合どうする？
            group_id = db.cursor(buffered=True)
            group_id.execute('SELECT id From Groups WHERE group_name = %s', (group_name,))
            group_id = group_id.fetchall()
            group_id = group_id[0][0]

            # 初期メンバー(自分の登録)、これは、一意のgroup_idだから大丈夫
            init_member = db.cursor(buffered=True)
            init_member.execute('INSERT INTO Members (member_id, flag_join, group_id) '
                                'VALUES (%s, %s, %s)',
                                (session['user_id'], 1, group_id,))
            db.commit()

            # 招待した人をmemberのmember_idに追加してflagを0にする
            for member in members:
                member = int(member)
                members = db.cursor(buffered=True)
                members.execute('INSERT INTO Members (member_id, flag_join, group_id) '
                                'VALUES (%s, %s, %s)', (member, 0, group_id,))
                db.commit()

            return redirect('/top')

        # ポップアップ2を追加---------------------------------------------------------------------------------------------------

        if request.method == "POST" and "follow" in request.form:
            db = cdb()
            # このやり方だと毎回ポップアップが消える (リダイレクトするから)
            id = request.form.get("follow")
            return_follow = db.cursor(buffered=True)
            return_follow.execute("INSERT INTO Follows (follow_id, followed_id) "
                                  "VALUES(%s, %s)", (session['user_id'], id,))
            db.commit()

            return redirect('/top')

        elif request.method == "POST" and "join_group" in request.form:
            db = cdb()
            id = request.form.get("join_group")
            join = db.cursor(buffered=True)
            join.execute("UPDATE Members SET flag_join = %s WHERE group_id = %s AND member_id = %s",
                         (1, id, session['user_id'],))
            db.commit()

            return redirect('/top')
        # ----------------------------------------------------------------------------------------------------------------

        else:
            db = cdb()
            if request.form.get("profile") == "プロフを表示する":
                session["profile_id"] = request.form.get("friend_id")
                session["profile_id"] = int(session["profile_id"])

                # clickの情報を保存する------------------------------------------------------------------------------------------
                if session["profile_id"] != session['user_id']:
                    date = datetime.date.today()
                    date = str(date)
                    date = date.replace("-", "")
                    add_click = db.cursor(buffered=True)
                    add_click.execute("INSERT INTO Clicks (click_id, clicked_id, flag, time_) VALUES (%s, %s, %s, %s)",
                                      (session['user_id'], session['profile_id'], 1, date))
                    db.commit()
                # ------------------------------------------------------------------------------------------------------------

                return redirect("/profile")

            elif request.form.get("myprofile") == "マイプロフを表示する":
                session["profile_id"] = request.form.get("my_id")
                # session["profile_id"] = int(session["profile_id"])
                session["profile_id"] = session["user_id"]
                return redirect("/profile")

            # elif request.form.get("to_group_talk") != None:
            #   session['room_id'] = request.form.get("group_id")
            #   db = cdb()
            #   get_group_name = db.cursor(buffered=True)
            #   get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
            #   session['room_name'] = get_group_name.fetchall()[0][0]

            #   get_group_name = db.cursor(buffered=True)
            #   get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
            #   session['room_name'] = get_group_name.fetchall()[0][0]
            #   return redirect("/talk")

            elif request.form.get("to_friend_talk") == "トークルームに行く":
                try:
                    get_group = db.cursor(buffered=True)

                    get_group.execute(
                        "SELECT id FROM Groups WHERE flag_group = %s AND id = (SELECT group_id FROM Members WHERE member_id IN (%s, %s) GROUP BY group_id HAVING COUNT(group_id) > 1)",
                        (0, session['user_id'], request.form.get('talk_id')))

                    session['room_id'] = get_group.fetchall()[0][0]
                    get_group_name = db.cursor()
                    get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
                    session['room_name'] = get_group_name.fetchall()[0][0]
                except:
                    session['room_id'] = request.form.get("talk_id")  # グループidにしたい
                    set_name = find_user(session['user_id']) + '&' + find_user(session['room_id'])

                    set_group = db.cursor(buffered=True)
                    set_group.execute("INSERT INTO Groups (group_name, flag_group) VALUES (%s, %s)", (set_name, 0))
                    db.commit()

                    group_id = db.cursor(buffered=True)
                    group_id.execute("SELECT id FROM Groups WHERE group_name = %s AND flag_group = %s", (set_name,0))
                    group = group_id.fetchall()[0][0]

                    into_group_user = db.cursor(buffered=True)
                    into_group_user.execute("INSERT INTO Members (member_id, group_id, flag_join) VALUES (%s, %s, %s)",
                                            (session['user_id'], group, 1))
                    db.commit()

                    into_group_follower = db.cursor(buffered=True)
                    into_group_follower.execute("INSERT INTO Members (member_id, group_id, flag_join) VALUES (%s, %s, %s)",
                                                (request.form.get('talk_id'), group, 1))
                    db.commit()

                    session['room_id'] = group

                get_group_name = db.cursor(buffered=True)
                get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
                session['room_name'] = get_group_name.fetchall()[0][0]
                return redirect("/talk")

            return "error"
    else:
        return redirect("/login")


@app.route("/asyncdata", methods=["GET", "POST"])
def asyncdata():
    db = cdb()
    if 'loggedin' in session:
        session['user_id'] = session['user_id']

        if request.method == "POST":
            if request.form.get("game_name") and request.form.get("game_level") and request.form.get("nickname"):
                msg = "同時には検索できません。"
                return render_template("search.html", n=msg)

            elif request.form.get("game_name") and request.form.get("game_level"):

                game_name = request.form.get("game_name")
                game_level = request.form.get("game_level")

                db = mysql.connector.connect(
                    user='root',
                    password='password',
                    host='db',
                    database='app'
                )

                # 選択肢のゲームネームの取得
                # game_names = db.cursor(buffered=True)
                # game_names.execute("SELECT game_name from Game_names")

                # ゲーム名とレベルで検索し、該当するIDを取得
                game_search = db.cursor(buffered=True)
                game_search.execute(
                    "SELECT user_id FROM Games INNER JOIN Game_names on Games.game_id = Game_names.id WHERE game_name = %s AND game_level = %s",
                    (game_name, game_level,))
                id_search = game_search.fetchall()

                # 取得したIDの中でログインユーザーとログインユーザーがフォローしている人のIDを抜き取る
                follow_id = db.cursor(buffered=True)
                follow_id.execute("SELECT followed_id from Follows where follow_id = %s", (session['user_id'],))
                follow_f = follow_id.fetchall()

                id_list = [i[0] for i in id_search]
                follow_list = [i[0] for i in follow_f]
                follow_list.append(session['user_id'])

                results = tuple(set(id_list) - set(follow_list))

                search_result = []

                for result in results:
                    game_list = []
                    profile_search = db.cursor(buffered=True)
                    profile_search.execute(
                        "SELECT P.id, P.nickname, P.icon, P.comment from Profiles as P where P.id = %s", (result,))
                    p = profile_search.fetchall()
                    p = list(p[0])

                    for i in range(1, 4):

                        game_search = db.cursor(buffered=True)
                        game_search.execute(
                            "SELECT G.game_order, G.game_level, N.Game_name from Games as G INNER JOIN Game_names as N ON G.game_id = N.id where G.user_id = %s and G.game_order = %s",
                            (result, i,))
                        g_list = game_search.fetchall()
                        g_list = list(g_list[0])

                        # search_result.append(g_list)
                        for g in g_list:
                            p.append(g)

                    search_result.append(p)

                return render_template("search.html", id_search=search_result)

            elif request.form.get("nickname"):

                l = []
                db = cdb()
                game_names = db.cursor(buffered=True)
                game_names.execute("SELECT game_name from Game_names")

                nickname = request.form.get("nickname")

                nick = db.cursor(buffered=True)
                nick.execute("SELECT P.id, P.nickname, P.icon, P.comment from Profiles as P where P.nickname = %s",
                             (nickname,))
                n = nick.fetchall()
                if len(n) == 0:
                    msg = "該当するユーザーはいませんでした"
                    return render_template("search.html", n=msg)

                n = list(n[0])

                for i in range(1, 4):

                    game_search = db.cursor(buffered=True)
                    game_search.execute(
                        "SELECT G.game_order, G.game_level, N.Game_name from Games as G INNER JOIN Game_names as N ON G.game_id = N.id where G.user_id = %s and G.game_order = %s",
                        (n[0], i,))
                    g_list = game_search.fetchall()
                    g_list = list(g_list[0])

                    for g in g_list:
                        n.append(g)

                l.append(n)

                return render_template("search.html", id_search=l)

            else:
                db = cdb()
                game_names = db.cursor(buffered=True)
                game_names.execute("SELECT game_name from Game_names")
                msg = "検索できませんでした。"
                return render_template("search.html", n=msg)

        if request.method == 'GET':
            num_users, num_items = setting()
            config = {'batch_size': 10, 'num_negative': 10,
                      'num_users': num_users, 'num_items': num_items,
                      'latent_dim': 4, 'alias': 'gmf_factor8neg4-implict',
                      'num_epoch': 100, 'l2_regularization': 0,
                      }
            data = get_data()
            df = preprocess_dataset(data)
            sample_generator = SampleGenerator(ratings=df)
            eval_data = sample_generator.evaluate_data
            negative_items = eval_data[3]
            train_loader = sample_generator.instance_a_train_loader(config['num_negative'], config['batch_size'])
            GMF_model = model(config)

            for epoch in range(3):
                train(GMF_model, train_loader)
            # torch.save(GMF_model.state_dict(), 'trained_dict.model')
            # torch.save(model, 'trained.model')

            t_, s_ = test_(GMF_model, eval_data)

            current_user = session['user_id']
            start = current_user * config['num_negative']
            end = ((current_user + 1) * config['num_negative'])
            prob_list = s_[start:end]
            prob_list_ = prob_list.tolist()
            index_list = negative_items[start:end]
            index_list_ = index_list.tolist()

            prob = []
            for i in prob_list_:
                for k in i:
                    prob.append(k)

            dic = {key: val for key, val in zip(index_list_, prob)}
            dic_sorted = dict(sorted(dic.items(), key=lambda x: x[1], reverse=True))
            keys = dic_sorted.keys()
            keys = list(keys)
            keys = [n + 1 for n in keys]
            mutual_list, Mutual_friends, followed_li = mutual_friend()
            mutual_list = list(mutual_list)
            double_m = mutual_list + mutual_list
            double_m.append(session['user_id'])
            double_m.append(session['user_id'])

            temp_list = keys + double_m
            reco_list = [x for x in temp_list if temp_list.count(x) == 1]

            search_result = []

            for result in reco_list:
                profile_search = db.cursor(buffered=True)
                profile_search.execute("SELECT P.id, P.nickname, P.icon, P.comment from Profiles as P where P.id = %s",
                                       (result,))
                p = profile_search.fetchall()
                p = list(p[0])

                for i in range(1, 4):

                    game_search = db.cursor(buffered=True)
                    game_search.execute(
                        "SELECT G.game_order, G.game_level, N.Game_name from Games as G INNER JOIN Game_names "
                        "as N ON G.game_id = N.id where G.user_id = %s and G.game_order = %s", (result, i,))
                    g_list = game_search.fetchall()
                    g_list = list(g_list[0])

                    for g in g_list:
                        p.append(g)

                search_result.append(p)

            return render_template('search.html', id_search=search_result)



@app.route('/group_pre', methods=['GET', 'POST'])
def group_pre():
    db = cdb()
    if request.method == 'POST' and 'edit' in request.form:
        session["group_id"] = request.form.get("edit")
        # session["group_id"] = int(session["group_id"])
        if request.form.get("to_group_talk") != None:
            session['room_id'] = int(request.form.get("edit"))

            get_group_name = db.cursor(buffered=True)
            get_group_name.execute("SELECT group_name FROM Groups WHERE id = %s", (session['room_id'],))
            session['room_name'] = get_group_name.fetchall()[0][0]

            return redirect('/talk')

        return redirect('/group_edit')


    else:
        group = db.cursor(buffered=True)
        group.execute("SELECT group_id FROM Members WHERE member_id= %s AND "
                      "flag_join= %s", (session['user_id'], 1,))
        group_id = group.fetchall()
        # groupはリストの中が()になっているからリストにする---------------------------------
        list_i = []
        for i in group_id:
            i = i[0]
            list_i.append(i)

        # groupで取ったidでGroupsテーブルからGroup_nameとGroup_iconを取得----------------
        group_list = []
        for i in list_i:
            id = db.cursor(buffered=True)
            id.execute(
                "SELECT group_name, group_icon, id from Groups where id = %s", (i,))
            m = id.fetchall()
            group_list.append(m)

        return render_template('group_pre.html', group=group_id, group_list=group_list)


@app.route('/group_edit', methods=['GET', 'POST'])
def group_edit():
    db = cdb()
    if request.method == "POST" and "kick" in request.form:
        id = request.form.get('kick')
        kick = db.cursor(buffered=True)
        kick.execute("DELETE FROM Members WHERE member_id = %s AND flag_join = %s",
                     (id, 1,))
        db.commit()
        return redirect('/group_edit')

    elif request.method == "POST" and "invite" in request.form:
        id = request.form.get('invite')
        invite = db.cursor(buffered=True)
        invite.execute("INSERT INTO Members (member_id, flag_join, group_id) "
                       "VALUES(%s, %s, %s)", (id, 0, session['group_id'],))
        db.commit()
        return redirect('/group_edit')

    if request.method == "POST":
        try:
            img_file = request.files['up_file']
            filename = secure_filename(img_file.filename)
            img_url = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            img_file.save(img_url)

            cursor = db.cursor(buffered=True)
            cursor.execute("UPDATE Groups SET group_icon = %s WHERE id = %s",
                           (UPLOAD_FOLDER + filename, session['group_id']))
            db.commit()
        except:
            pass

        if "group_name" in request.form:
            set_name = db.cursor(buffered=True)
            set_name.execute("UPDATE Groups SET group_name = %s WHERE id = %s",
                             (request.form.get("group_name"), session['group_id'],))
            db.commit()

        return redirect('/group_edit')


    else:
        group = db.cursor(buffered=True)
        group.execute("SELECT group_name, group_icon FROM Groups WHERE id = %s",
                      (session['group_id'],))
        group = group.fetchall()
        # Mutual ---------------------------------------------------------------------------------------------
        Mutuals, Mutual_friends, followed_li = mutual_friend()
        # Mutual -----------------------------------------------------------------------------------------
        # current user
        user_id = session['user_id']

        # グループ参加者
        group_member = db.cursor(buffered=True)
        group_member.execute("SELECT member_id FROM Members WHERE group_id = %s AND flag_join = %s",
                             (session['group_id'], 1,))
        list_group_member = []
        for i in group_member:
            i = i[0]
            list_group_member.append(i)

        list_group_except_me = []
        for i in list_group_member:
            if i == session['user_id']:
                pass
            else:
                list_group_except_me.append(i)

        invited = db.cursor(buffered=True)
        invited.execute("SELECT member_id FROM Members WHERE group_id = %s AND flag_join = %s",
                        (session['group_id'], 0,))
        list_invited = []
        for i in invited:
            i = i[0]
            list_invited.append(i)

        group_related = list_invited + list_group_except_me  # list_group_except_me -> 自分以外のすでに入っている人 list_invited -> いま招待されている人
        temp_1 = list(set(Mutuals)) + list(set(group_related))
        fix = []

        not_invited = [x for x in set(temp_1) if temp_1.count(x) == 1]

        results = tuple(set(not_invited) - set(list_invited))

        not_invited = list(results)

        current = db.cursor(buffered=True)
        current.execute("SELECT icon, nickname, id from Profiles where id = %s",
                        (session['user_id'],))
        current = current.fetchall()

        group_joined = []
        for i in list_group_except_me:
            list_friends = db.cursor(buffered=True)
            list_friends.execute("SELECT icon, nickname, id from Profiles where id = %s", (i,))
            m = list_friends.fetchall()
            group_joined.append(m)

        already_invited = []
        for i in list_invited:
            list_friends = db.cursor(buffered=True)
            list_friends.execute("SELECT icon, nickname, id from Profiles where id = %s", (i,))
            m = list_friends.fetchall()
            already_invited.append(m)

        not_invited_ = []
        for i in not_invited:
            list_friends = db.cursor(buffered=True)
            list_friends.execute("SELECT icon, nickname, id from Profiles where id = %s", (i,))
            m = list_friends.fetchall()
            not_invited_.append(m)

        return render_template('group_edit.html', group=group, current=current,
                               not_invited_=not_invited_, group_joined=group_joined,
                               already_invited=already_invited)


@app.route("/admin", methods=['GET', 'POST'])
def admin():
    db = cdb()
    if request.method == "POST":
        set_prof = db.cursor(buffered=True)
        set_prof.execute("UPDATE Profiles SET nickname = %s WHERE id = %s", (request.form.get("nickname"), request.form.get("userid")))
        db.commit()

        show_user = db.cursor(buffered=True)
        show_user.execute("SELECT nickname FROM Profiles")
        show_users = show_user.fetchall()
        return render_template("admin.html", show_users=show_users)
    else:
        show_user = db.cursor(buffered=True)
        show_user.execute("SELECT nickname FROM Profiles")
        show_users = show_user.fetchall()
        return render_template("admin.html", show_users=show_users)


if __name__ == '__main__':
    socketio.run(app, debug=True)
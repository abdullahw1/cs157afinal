"""This module holds all the flask routes of our app (all URL paths) 
and incharge of the frontend for rendering html templates.

The standarn convention of defining a route here is:

```python
@myapp_obj.route("/my-route")
def my_route():
    # Code here
    return render_template("my_route.html")
```

Or we could redirect to an existing route using:

```python
@myapp_obj.route("/my-route1")
def my_route1():
    # Code here
    return redirect(url_for("my_route"))
```

Detailed flask documentation can be found [here](https://flask.palletsprojects.com/en/2.0.x/api/).

"""

import os
import tempfile
import random
import pathlib
from datetime import datetime
import markdown
from base64 import b64encode
from flask import render_template, flash, redirect, url_for, request, jsonify, abort, send_file
from werkzeug.security import generate_password_hash
from flask_login import current_user, login_user, logout_user, login_required
from xhtml2pdf import pisa
from werkzeug.utils import secure_filename


from myapp import myapp_obj, db
from myapp.forms import SignupForm, LoginForm, FlashCardForm, UploadMarkdownForm, SearchForm, ShareFlashCardForm, NextButton, ObjectiveForm
from myapp.models import User, FlashCard, Friend, FriendStatusEnum, SharedFlashCard
from myapp.models_methods import get_friend_status, get_all_friends
from myapp.mdparser import md2flashcard

basedir = os.path.abspath(os.path.dirname(__file__))

@myapp_obj.context_processor
def jinja_encode_to_b64():
    def encode_to_b64(blob):
        return b64encode(blob).decode("utf-8")
    return dict(encode_to_b64=encode_to_b64)


@myapp_obj.route("/")
def home():
    """Homepage route"""
    return render_template("homepage.html")


@myapp_obj.route("/signup", methods=['GET', 'POST'])
def signup():
    """Signup page route"""
    if current_user.is_authenticated:
        return redirect(url_for("log"))
    form = SignupForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        user = User(email=form.email.data, username=form.username.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash("Your account has been created. You can now login")
        return redirect(url_for("home"))

    return render_template("signup.html", form=form)


@myapp_obj.route("/login", methods=['GET', 'POST'])
def login():
    """Login page route"""
    if current_user.is_authenticated:
        return redirect(url_for("log"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is not None and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            flash(f'Logged in as User "{form.username.data}", remember_me={form.remember_me.data}')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for("log"))
        else:
            flash("Login invalid username or password!", "error")
            return redirect('/login')
    return render_template("login.html", form=form)


@myapp_obj.route("/loggedin")
@login_required
def log():
    """User logged in route, this redirects to homepage"""
    return render_template("/homepage.html")


@myapp_obj.route("/logout")
@login_required
def logout():
    """User logged out route, this logout the user and redirects to homepage"""
    logout_user()
    return redirect(url_for("home"))


AVATAR_IMGS = {
    1: 'images/clipart722174.png',
    2: 'images/clipart722180.png',
    3: 'images/clipart1236782.png',
    4: 'images/clipart1236792.png',
    5: 'images/clipart1237041.png',
    6: 'images/clipart1237090.png',
}

@myapp_obj.route("/account")
@login_required
def account():
    """User's account page, redirect if need to change avatar"""

    return render_template("/account.html", avatars=AVATAR_IMGS)


@myapp_obj.route("/change_avatar/<int:avatar_id>")
@login_required
def change_avatar(avatar_id):
    """To switch avatar pictures and more, then redirect back to account"""
    if avatar_id in AVATAR_IMGS:
        avatar_path = os.path.join(basedir, f'./static/{AVATAR_IMGS[avatar_id]}')
        if os.path.exists(avatar_path):
            user = current_user._get_current_object()
            with open(avatar_path, 'rb') as fp:
                user.avatar = fp.read() # Modify avatar blob
                db.session.commit()
        else:
            raise Exception(f"Avatar {avatar_path} doesn't exists")
    return redirect(url_for("account"))


@myapp_obj.route("/add-flashcard", methods=['GET', 'POST'])
@login_required
def add_flashcard():
    """Add flashcard page route, allow user to use FlashCardForm to add a new flashcard"""
    form = FlashCardForm()
    if form.validate_on_submit():
        card = FlashCard(front=form.front.data, back=form.back.data, view=0, learned=0, user=current_user._get_current_object())
        db.session.add(card)
        db.session.commit()
        flash("Flashcard has been created", "success")
        return redirect(url_for("add_flashcard"))
    return render_template("/add-flashcard.html", form=form)


@myapp_obj.route("/my-flashcards")
@login_required
def show_flashcard():
    """My Flashcard route, to show all flashcard of current user by order based on how often user got answer correct"""
    ordered_cards = FlashCard.query.filter_by(user_id=current_user.get_id()).order_by(FlashCard.learned).all()
    if not ordered_cards:
        flash("You don't have any flashcards. Please create one", "warning")
        return redirect(url_for("add_flashcard"))
    return render_template("my-flashcards.html", ordered_cards=ordered_cards)


def _shuffle_choices(current_card, cards):
    """Generate the choices for learn-flashcards feature"""
    card_id = current_card.id
    numbers = [x.id for x in cards]
    numbers.remove(card_id) 
    random.shuffle(numbers)
    lst_id = []
    for i in range (3):
        temp = numbers.pop()
        lst_id.append(temp)
    lst_id.append(card_id)
    random.shuffle(lst_id)
    return lst_id


@myapp_obj.route("/import-flashcard", methods=['GET', 'POST'])
@login_required
def import_flashcard():
    """Import Flashcard route, for user to import markdown file into flashcard"""
    form = UploadMarkdownForm()
    if form.validate_on_submit():
        f = form.file.data
        content = f.stream.read().decode('ascii')
        for section, flashcards in md2flashcard(content).items(): # TODO: Save flashcard by section
            for flashcard in flashcards:
                card = FlashCard(front=flashcard.front, back=flashcard.back, learned=0,  user=current_user._get_current_object())
                db.session.add(card)
        db.session.commit()
        flash(f'Uploaded file {f.filename} into flashcards')
        return redirect(url_for("show_flashcard"))
    return render_template("import-flashcard.html", form=form)


@myapp_obj.route("/learn-flashcard", methods=['GET', 'POST'])
@login_required
def learn_flashcard():
    """Learn Flashcard route, for user to learn from all it's existing flashcards in My Flashcards"""
    first_card = FlashCard.query.filter_by(user_id=current_user.get_id()).order_by(FlashCard.learned, FlashCard.view).first()
    cards = FlashCard.query.filter_by(user_id=current_user.get_id()).all() # list of cards that the current user has

    if len(cards) < 4:
        flash("You must have at least 4 flashcards. Please create more flashcards", "warning")
        return redirect(url_for("add_flashcard"))
    
    form = ObjectiveForm()
    formNext = NextButton()
    list_id = _shuffle_choices(first_card, cards)
    choice = [FlashCard.query.get(x) for x in list_id]

    correct_choice = None
    if form.validate_on_submit():
        if form.A.data:
            if form.A.raw_data[0] == first_card.back:
                correct_choice = True
            else:
                correct_choice = False
        elif form.B.data:
            if form.B.raw_data[0] == first_card.back:
                correct_choice = True
            else:
                correct_choice = False
        elif form.C.data:
            if form.C.raw_data[0] == first_card.back:
                correct_choice = True
            else:
                correct_choice = False
        elif form.D.data:
            if form.D.raw_data[0] == first_card.back:
                correct_choice = True
            else:
                correct_choice = False
        # If form submitted
        if correct_choice is not None:
            # If correct choice
            if correct_choice:
                flash('Excellent', "success")
                correct_choice = first_card.back # Pass this to html template so it will render this as card instead of ABCD options
                first_card.learned += 1
                db.session.commit()
            else:
                flash('opps. Wrong answer', "error")
    else:
        if formNext.validate_on_submit():
            first_card.view += 1
            db.session.commit()
            return redirect(url_for("learn_flashcard"))

    form.A.label.text = choice[0].back
    form.B.label.text = choice[1].back
    form.C.label.text = choice[2].back
    form.D.label.text = choice[3].back
    return render_template("learn-flashcard.html", first_card=first_card, form=form, formNext=formNext, choice=choice, list_id=list_id, correct_choice=correct_choice)


@myapp_obj.route("/download-flashcard-as-pdf", methods=['GET', 'POST'])
@login_required
def download_flashcard_as_pdf():
    """Download Flashcards to a single PDF file, then it will redirect user back to My Flashcards"""
    ordered_cards = FlashCard.query.filter_by(user_id=current_user.get_id()).order_by(FlashCard.learned).all()
    # Handle case of no flashcard
    if not ordered_cards:
        abort(404, description="No flashcards found, cannot download as pdf")
    # Generate markdown content
    cards = []
    for idx, card in enumerate(ordered_cards): # Generate a markdown card for each card
        cards.append(f'\n---\n\n**{card.front}**\n\n?\n\n{card.back}\n\n---\n\n')
    cards_text = '\n'.join(cards)
    md_text = '## Flashcards\n\n' + cards_text
    # Covert to html
    html = markdown.markdown(md_text)
    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_filename = os.path.join(temp_dir, 'flashcards.pdf')
        # Convert html to pdf
        with open(pdf_filename, "wb+") as fp:
            pisa_status = pisa.CreatePDF(html, dest=fp)
        return send_file(pdf_filename, as_attachment=True)


@myapp_obj.route("/remove-flashcard/<int:flashcard_id>", methods=['GET', 'POST'])
@login_required
def remove_flashcard(flashcard_id):
    """A route to remove a flashcard from user's MyFlashCard,
    this will redirect back to My Flashcards after removing the specified card
    """
    flashcard = FlashCard.query.filter_by(id=flashcard_id).one_or_none()
    if flashcard:
        flash(f'Deleted flashcard front="{flashcard.front}", back="{flashcard.back}"')
        db.session.delete(flashcard)
        db.session.commit()
    return redirect(url_for("show_flashcard"))


@myapp_obj.route("/share-flashcard/<int:flashcard_id>", methods=['GET', 'POST'])
@login_required
def share_flashcard(flashcard_id):
    """A route for user to use the ShareFlashCardForm to select which friend they
    want to share the specified flashcard with.
    """
    flashcard = FlashCard.query.filter_by(id=flashcard_id).one_or_none()
    if not flashcard:
        abort(404, Description=f'Unable to find flashcard with id {flashcard_id}')
    friends = []
    for status, oth_user in get_all_friends(current_user.get_id()):
        if status == 'friend': # Only find friends
            friends.append(oth_user)
    form = ShareFlashCardForm()
    form.dropdown.choices = [(u.id, u.username) for u in friends]
    if form.validate_on_submit():
        user = User.query.filter_by(id=form.dropdown.data).one()
        now = datetime.now()
        share_card = SharedFlashCard(flashcard_id=flashcard_id,
                                    datetime=now,
                                    owner_user_id=current_user.get_id(),
                                    target_user_id=user.id)
        db.session.add(share_card)
        db.session.commit()
        flash(f'Shared flashcard(#{flashcard_id}) to "{user.username}" on {str(now)}')
        return redirect(url_for("show_flashcard"))
    return render_template("share-flashcard.html", flashcard=flashcard, form=form)


@myapp_obj.route("/flashcards-sharing", methods=['GET', 'POST'])
@login_required
def flashcards_sharing():
    """A route for viewing sharing status of flashcards (both shared to others and others shared to me)"""
    owner_flashcards = SharedFlashCard.query.filter_by(owner_user_id=current_user.get_id()).all()
    target_flashcards = SharedFlashCard.query.filter_by(target_user_id=current_user.get_id()).all()
    return render_template("flashcards-sharing.html", owner_flashcards=owner_flashcards, target_flashcards=target_flashcards)


@myapp_obj.route("/flashcards-sharing/add-to-myflashcards/<int:sharing_id>", methods=['GET', 'POST'])
@login_required
def flashcards_sharing_add_to_myflashcards(sharing_id):
    """A route for adding shared flashcard that other user shared into My FlashCards"""
    sharing = SharedFlashCard.query.get(sharing_id)
    if int(current_user.get_id()) != sharing.owner_user_id and\
        int(current_user.get_id()) != sharing.target_user_id:
        abort(404, description='Invalid permission')
    card = FlashCard(front=sharing.flashcard.front, back=sharing.flashcard.back, learned=0, user=current_user._get_current_object())
    db.session.add(card)
    db.session.commit()
    flash(f'Copied flashcard(#{sharing.flashcard.id}) to "My Flashcards", new flashcard(#{card.id})')
    return redirect(url_for('flashcards_sharing'))


@myapp_obj.route("/flashcards-sharing/cancel-sharing/<int:sharing_id>", methods=['GET', 'POST'])
@login_required
def flashcards_sharing_cancel_sharing(sharing_id):
    """A route for cancelling a flashcard sharing"""
    sharing = SharedFlashCard.query.get(sharing_id)
    if int(current_user.get_id()) != sharing.owner_user_id and\
        int(current_user.get_id()) != sharing.target_user_id:
        abort(404, description='Invalid permission')
    flash(f'Sharing of flashcard(#{sharing.flashcard.id}) cancelled')
    db.session.delete(sharing)
    db.session.commit()
    return redirect(url_for('flashcards_sharing'))


# Friends
@myapp_obj.route("/my-friends", methods=['GET', 'POST'])
@login_required
def show_friends():
    """My Friends route for viewing all friends and accepting/rejecting pending friend requests"""
    # Handle show all friends
    friends = []
    for status, oth_user in get_all_friends(current_user.get_id()):
        if status == 'friend':
            buttons = [(f'/remove-friend/{oth_user.id}', 'Remove Friend', 'btn-outline-danger')] #Tuple in the format (link, text, button_type)
            print_status = 'Friend'
        elif status == 'pending-sent-request':
            buttons = [(f'/remove-friend/{oth_user.id}', 'Unsend', 'btn-outline-warning')]
            print_status = 'Sent'
        elif status == 'pending-to-approve':
            buttons = [(f'/add-friend/{oth_user.id}', 'Approve', 'btn-outline-success'),
                        (f'/remove-friend/{oth_user.id}', 'Reject', 'btn-outline-danger')
                    ]
            print_status = 'Pending'
        else:
            abort(404, f'Unknown status {status}')
        friends.append((oth_user, print_status, buttons))
    # Handle Add user
    found_users = []
    search_form = SearchForm()
    if search_form.validate_on_submit():
        search_str = search_form.text.data
        result = User.query.filter(User.username.contains(search_str) & (User.id != (current_user.get_id()))).all()
        for user in result:
            status, _ = get_friend_status(current_user.get_id(), user.id)
            if status == 'friend':
                buttons = [(f'/remove-friend/{user.id}', 'Remove Friend', 'btn-outline-danger')]
            elif status == 'pending-sent-request':
                buttons = [(f'/remove-friend/{user.id}', 'Unsend', 'btn-outline-warning')]
            elif status == 'pending-to-approve':
                buttons = [(f'/add-friend/{user.id}', 'Approve', 'btn-outline-success'),
                            (f'/remove-friend/{user.id}', 'Reject', 'btn-outline-danger')
                        ]
            elif status == 'neutral':
                buttons = [(f'/add-friend/{user.id}', 'Add Friend', 'btn-outline-info')]
            else:
                abort(404, description=f'Unknown status {status}')
            found_users.append((user.username, buttons))
    return render_template("my-friends.html", friends=friends, search_form=search_form, found_users=found_users)


@myapp_obj.route("/add-friend/<int:user_id>", methods=['GET', 'POST'])
@login_required
def add_friend_userid_provided(user_id):
    """A route for handling an add friend request, this will redirect back to MyFriends page"""
    # Abort if adding self as friend
    if int(current_user.get_id()) == user_id:
        return abort(404, description="Cannot add yourself as friend")
    status, friend_record = get_friend_status(current_user.get_id(), user_id)
    if status == 'friend':
        # Already a friend, do nothing
        pass
    elif status == 'pending-sent-request':
        # Current user sent a request, do nothing
        flash(f'Friend request already sent to "{friend_record.user2.username}"', "warning")
    elif status == 'pending-to-approve':
        # Other user sent the request, approve (Change status from pending to approved)
        friend_record.status = FriendStatusEnum.FRIEND
        db.session.add(friend_record)
        db.session.commit()
        flash(f'Approved friend request from "{friend_record.user1.username}"')
    elif status == 'neutral':
        # No friendship record found, send friend request
        user = User.query.filter_by(id=user_id).one()
        friend = Friend(user1_id=current_user.get_id(), user2_id=user.id, status=FriendStatusEnum.PENDING)
        db.session.add(friend)
        db.session.commit()
        flash(f'Sent friend request to "{user.username}"')
    else:
        abort(404, description=f"Unknown status {status}")
    return redirect(url_for("show_friends"))


@myapp_obj.route("/remove-friend/<int:user_id>", methods=['GET', 'POST'])
@login_required
def remove_friend_userid_provided(user_id):
    """A route for handling cancel sent friend request and reject freind request,
    this will then redirect back to MyFriends page
    """
    # Abort if removing self as friend
    if int(current_user.get_id()) == user_id:
        return abort(404, description="Cannot remove yourself from friend")
    status, friend_record = get_friend_status(current_user.get_id(), user_id)
    if friend_record:
        other_user = friend_record.user1.username if friend_record.user1.id != int(current_user.get_id()) else friend_record.user2.username
        if status == 'friend':
            flash(f'Removed "{other_user}" from friend')
        elif status == 'pending-sent-request':
            flash(f'Unsent friend request to "{other_user}"')
        elif status == 'pending-to-approve':
            flash(f'Rejected friend request from "{other_user}"')
        elif status == 'neutral':
            pass # Do nothing
        else:
            abort(404, description=f'Unknown status {status}')
        db.session.delete(friend_record)
        db.session.commit()
    return redirect(url_for("show_friends"))


#Pomodoro app
@myapp_obj.route("/pomodoro")
def tomato():
    """Show Pomodoro timer route"""
    return render_template("/pomodoro.html")



@myapp_obj.errorhandler(404)
def page_not_found(e):
    """Handler error404 and print out description of error"""
    return jsonify(error=str(e)), 404


myapp_obj.register_error_handler(404, page_not_found)


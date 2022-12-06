from myapp import myapp_obj, db

DEBUG = False
PORT_NUMBER = 5099

def launch_browser():
    webbrowser.open(f'http://localhost:{PORT_NUMBER}', new=0)


# Create *.db file from schema (if doesn't exists)
try:
    db.create_all()
except:
    pass

# Disabled autolaunch browser to deploy heroku
#if not DEBUG:
#    threading.Timer(1, launch_browser).start()

# Run flask app server

myapp_obj.run(debug=DEBUG, port=PORT_NUMBER)
if __name__ == '__main__':
    myapp_obj.run(debug=DEBUG)

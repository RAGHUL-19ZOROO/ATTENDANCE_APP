from core import app


from ROUTES.auth_routes import bp as auth_bp
from ROUTES.principal_routes import bp as principal_bp
from ROUTES.classrep_routes import bp as classrep_bp
from ROUTES.attendance_routes import bp as attendance_bp
from ROUTES.hod_routes import bp as hod_bp

app.register_blueprint(auth_bp)
app.register_blueprint(principal_bp)
app.register_blueprint(classrep_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(hod_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

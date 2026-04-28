from livereload import Server
from sindhu import web


def main():
    options = web.get_program_options()
    app = web.create_app()
    app.debug = options.debug

    # app.run(debug=options.debug, host=options.host, port=int(options.port))

    server = Server(app.wsgi_app)
    server.watch("sindhu/web/")
    server.serve(
        host=options.host,
        port=int(options.port),
        debug=options.debug,
        restart_delay=2,
    )

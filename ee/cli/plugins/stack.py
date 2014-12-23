"""Example Plugin for EasyEngine."""

from cement.core.controller import CementBaseController, expose
from cement.core import handler, hook
from ee.core.variables import EEVariables
from ee.core.aptget import EEAptGet
from ee.core.download import EEDownload
from ee.core.shellexec import EEShellExec
from ee.core.fileutils import EEFileUtils
from ee.core.apt_repo import EERepo
from ee.core.extract import EEExtract
from ee.core.mysql import EEMysql
from pynginxconfig import NginxConfig
import random
import string
import configparser
import time
import shutil
import os
import pwd
import grp
from ee.cli.plugins.stack_services import EEStackStatusController


def ee_stack_hook(app):
    # do something with the ``app`` object here.
    pass


class EEStackController(CementBaseController):
    class Meta:
        label = 'stack'
        stacked_on = 'base'
        stacked_type = 'nested'
        description = 'stack command manages stack operations'
        arguments = [
            (['--web'],
                dict(help='Install web stack', action='store_true')),
            (['--admin'],
                dict(help='Install admin tools stack', action='store_true')),
            (['--mail'],
                dict(help='Install mail server stack', action='store_true')),
            (['--nginx'],
                dict(help='Install Nginx stack', action='store_true')),
            (['--php'],
                dict(help='Install PHP stack', action='store_true')),
            (['--mysql'],
                dict(help='Install MySQL stack', action='store_true')),
            (['--postfix'],
                dict(help='Install Postfix stack', action='store_true')),
            (['--wpcli'],
                dict(help='Install WPCLI stack', action='store_true')),
            (['--phpmyadmin'],
                dict(help='Install PHPMyAdmin stack', action='store_true')),
            (['--adminer'],
                dict(help='Install Adminer stack', action='store_true')),
            (['--utils'],
                dict(help='Install Utils stack', action='store_true')),
            ]

    @expose(hide=True)
    def default(self):
        # TODO Default action for ee stack command
        print("Inside EEStackController.default().")

    @expose(hide=True)
    def pre_pref(self, apt_packages):
        if set(EEVariables.ee_postfix).issubset(set(apt_packages)):
            print("Pre-seeding postfix variables ... ")
            EEShellExec.cmd_exec("echo \"postfix postfix/main_mailer_type "
                                 "string 'Internet Site'\" | "
                                 "debconf-set-selections")
            EEShellExec.cmd_exec("echo \"postfix postfix/mailname string "
                                 "$(hostname -f)\" | debconf-set-selections")
        if set(EEVariables.ee_mysql).issubset(set(apt_packages)):
            print("Adding repository for mysql ... ")
            EERepo.add(repo_url=EEVariables.ee_mysql_repo)
            EERepo.add_key('1C4CBDCDCD2EFD2A')
            chars = ''.join(random.sample(string.ascii_letters, 8))
            print("Pre-seeding mysql variables ... ")
            EEShellExec.cmd_exec("echo \"percona-server-server-5.6 "
                                 "percona-server-server/root_password "
                                 "password {chars}\" | "
                                 "debconf-set-selections".format(chars=chars))
            EEShellExec.cmd_exec("echo \"percona-server-server-5.6 "
                                 "percona-server-server/root_password_again "
                                 "password {chars}\" | "
                                 "debconf-set-selections".format(chars=chars))
            mysql_config = """
            [mysqld]
            user = root
            password = {chars}
            """.format(chars=chars)
            config = configparser.ConfigParser()
            config.read_string(mysql_config)
            with open(os.path.expanduser("~")+'/.my.cnf', 'w') as configfile:
                config.write(configfile)

        if set(EEVariables.ee_nginx).issubset(set(apt_packages)):
            print("Adding repository for nginx ... ")
            if EEVariables.ee_platform_distro == 'Debian':
                EERepo.add(repo_url=EEVariables.ee_nginx_repo)
            else:
                EERepo.add(ppa=EEVariables.ee_nginx_repo)

        if set(EEVariables.ee_php).issubset(set(apt_packages)):
            print("Adding repository for php ... ")
            if EEVariables.ee_platform_distro == 'Debian':
                EERepo.add(repo_url=EEVariables.ee_php_repo)
                EERepo.add_key('89DF5277')
            else:
                EERepo.add(ppa=EEVariables.ee_php_repo)

        if set(EEVariables.ee_dovecot).issubset(set(apt_packages)):
            if EEVariables.ee_platform_codename == 'squeeze':
                print("Adding repository for dovecot ... ")
                EERepo.add(repo_url=EEVariables.ee_dovecot_repo)

            EEShellExec.cmd_exec("echo \"dovecot-core dovecot-core/"
                                 "create-ssl-cert boolean yes\" "
                                 "| debconf-set-selections")
            EEShellExec.cmd_exec("echo \"dovecot-core dovecot-core/ssl-cert-"
                                 "name string $(hostname -f)\""
                                 " | debconf-set-selections")

    @expose(hide=True)
    def post_pref(self, apt_packages, packages):
        if len(apt_packages):
            if set(EEVariables.ee_postfix).issubset(set(apt_packages)):
                pass
            if set(EEVariables.ee_nginx).issubset(set(apt_packages)):
                # Nginx core configuration change using configparser
                nc = NginxConfig()
                print('in nginx')
                nc.loadf('/etc/nginx/nginx.conf')
                nc.set('worker_processes', 'auto')
                nc.append(('worker_rlimit_nofile', '100000'), position=2)
                nc.remove(('events', ''))
                nc.append({'name': 'events', 'param': '', 'value':
                           [('worker_connections', '4096'),
                            ('multi_accept', 'on')]}, position=4)
                nc.set([('http',), 'keepalive_timeout'], '30')
                nc.savef('/etc/nginx/nginx.conf')

                # Custom Nginx configuration by EasyEngine
                data = dict(version='EasyEngine 3.0.1')
                ee_nginx = open('/etc/nginx/conf.d/ee-nginx.conf', 'w')
                self.app.render((data), 'nginx-core.mustache', out=ee_nginx)
                ee_nginx.close()

            if set(EEVariables.ee_php).issubset(set(apt_packages)):
                # Parse etc/php5/fpm/php.ini
                config = configparser.ConfigParser()
                config.read('/etc/php5/fpm/php.ini')
                config['PHP']['expose_php'] = 'Off'
                config['PHP']['post_max_size'] = '100M'
                config['PHP']['upload_max_filesize'] = '100M'
                config['PHP']['max_execution_time'] = '300'
                config['PHP']['date.timezone'] = time.tzname[time.daylight]
                with open('/etc/php5/fpm/php.ini', 'w') as configfile:
                    config.write(configfile)

                # Prase /etc/php5/fpm/php-fpm.conf
                config = configparser.ConfigParser()
                config.read('/etc/php5/fpm/php-fpm.conf')
                config['global']['error_log'] = '/var/log/php5/fpm.log'
                with open('/etc/php5/fpm/php-fpm.conf', 'w') as configfile:
                    config.write(configfile)

                # Parse /etc/php5/fpm/pool.d/www.conf
                config = configparser.ConfigParser()
                config.read('/etc/php5/fpm/pool.d/www.conf')
                config['www']['ping.path'] = '/ping'
                config['www']['pm.status_path'] = '/status'
                config['www']['pm.max_requests'] = '500'
                config['www']['pm.max_children'] = ''
                config['www']['pm.start_servers'] = '20'
                config['www']['pm.min_spare_servers'] = '10'
                config['www']['pm.max_spare_servers'] = '30'
                config['www']['request_terminate_timeout'] = '300'
                config['www']['pm'] = 'ondemand'
                config['www']['listen'] = '127.0.0.1:9000'
                with open('/etc/php5/fpm/pool.d/www.conf', 'w') as configfile:
                    config.write(configfile)

            if set(EEVariables.ee_mysql).issubset(set(apt_packages)):
                config = configparser.ConfigParser()
                config.read('/etc/mysql/my.cnf')
                config['mysqld']['wait_timeout'] = 30
                config['mysqld']['interactive_timeout'] = 60
                config['mysqld']['performance_schema'] = 0
                with open('/etc/mysql/my.cnf', 'w') as configfile:
                    config.write(configfile)

            if set(EEVariables.ee_dovecot).issubset(set(apt_packages)):
                EEShellExec.cmd_exec("adduser --uid 5000 --home /var/vmail"
                                     "--disabled-password --gecos '' vmail")
                EEShellExec.cmd_exec("openssl req -new -x509 -days 3650 -nodes"
                                     " -subj /commonName={HOSTNAME}/emailAddre"
                                     "ss={EMAIL} -out /etc/ssl/certs/dovecot."
                                     "pem -keyout /etc/ssl/private/dovecot.pem"
                                     .format(HOSTNAME=EEVariables.ee_fqdn,
                                             EMAIL=EEVariables.ee_email))
                EEShellExec.cmd_exec("chmod 0600 /etc/ssl/private/dovecot.pem")

                # Custom Dovecot configuration by EasyEngine
                data = dict()
                ee_dovecot = open('/etc/dovecot/conf.d/99-ee.conf', 'w')
                self.app.render((data), 'dovecot.mustache', out=ee_dovecot)
                ee_dovecot.close()

                # Custom Postfix configuration needed with Dovecot
                # Changes in master.cf
                # TODO: Find alternative for sed in Python
                EEShellExec.cmd_exec("sed -i 's/#submission/submission/'"
                                     "/etc/postfix/master.cf")
                EEShellExec.cmd_exec("sed -i 's/#smtps/smtps/'"
                                     " /etc/postfix/master.cf")

                EEShellExec.cmd_exec("postconf -e \"smtpd_sasl_type ="
                                     " dovecot\"")
                EEShellExec.cmd_


        if len(packages):
            if any('/usr/bin/wp' == x[1] for x in packages):
                EEShellExec.cmd_exec("chmod +x /usr/bin/wp")
            if any('/tmp/pma.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/pma.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/22222/htdocs/db'):
                    os.makedirs('/var/www/22222/htdocs/db')
                shutil.move('/tmp/phpmyadmin-STABLE/',
                            '/var/www/22222/htdocs/db/pma/')
                EEShellExec.cmd_exec('chown -R www-data:www-data '
                                     '/var/www/22222/htdocs/db/pma')
            if any('/tmp/memcache.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/memcache.tar.gz',
                                  '/var/www/22222/htdocs/cache/memcache')
                EEShellExec.cmd_exec('chown -R www-data:www-data '
                                     '/var/www/22222/htdocs/cache/memcache')

            if any('/tmp/webgrind.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/webgrind.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/22222/htdocs/php'):
                    os.makedirs('/var/www/22222/htdocs/php')
                shutil.move('/tmp/webgrind-master/',
                            '/var/www/22222/htdocs/php/webgrind')
                EEShellExec.cmd_exec('chown -R www-data:www-data '
                                     '/var/www/22222/htdocs/php/webgrind/')

            if any('/tmp/anemometer.tar.gz' == x[1]
                    for x in packages):
                EEExtract.extract('/tmp/anemometer.tar.gz', '/tmp/')
                if not os.path.exists('/var/www/22222/htdocs/db/'):
                    os.makedirs('/var/www/22222/htdocs/db/')
                shutil.move('/tmp/Anemometer-master',
                            '/var/www/22222/htdocs/db/anemometer')
                chars = ''.join(random.sample(string.ascii_letters, 8))
                anemometer_db = EEMysql()
                EEShellExec.cmd_exec('mysql < /var/www/22222/htdocs/db'
                                     '/anemometer/install.sql')
                anemometer_db.execute('grant select on *.* to \'anemometer\''
                                      '@\'localhost\'')
                anemometer_db.execute('grant all on slow_query_log.* to'
                                      '\'anemometer\'@\'localhost\' IDENTIFIED'
                                      ' BY \''+chars+'\'')
                anemometer_db.close()
                # Custom Anemometer configuration
                data = dict(host='localhost', port='3306', user='anemometer',
                            password=chars)
                ee_anemometer = open('/var/www/22222/htdocs/db/anemometer'
                                     '/conf/config.inc.php', 'w')
                self.app.render((data), 'anemometer.mustache',
                                out=ee_anemometer)
                ee_anemometer.close()

            if any('/usr/bin/pt-query-advisor' == x[1]
                    for x in packages):
                EEShellExec.cmd_exec("chmod +x /usr/bin/pt-query-advisor")
        pass

    @expose()
    def install(self):
        pkg = EEAptGet()
        apt_packages = []
        packages = []

        if self.app.pargs.web:
            apt_packages = (apt_packages + EEVariables.ee_nginx +
                            EEVariables.ee_php + EEVariables.ee_mysql)
        if self.app.pargs.admin:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.mail:
            apt_packages = apt_packages + EEVariables.ee_dovecot
        if self.app.pargs.nginx:
            apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.php:
            apt_packages = apt_packages + EEVariables.ee_php
        if self.app.pargs.mysql:
            apt_packages = apt_packages + EEVariables.ee_mysql
        if self.app.pargs.postfix:
            apt_packages = apt_packages + EEVariables.ee_postfix
        if self.app.pargs.wpcli:
            packages = packages + [["https://github.com/wp-cli/wp-cli/releases"
                                    "/download/v0.17.1/wp-cli.phar",
                                    "/usr/bin/wp"]]
        if self.app.pargs.phpmyadmin:
            packages = packages + [["https://github.com/phpmyadmin/phpmyadmin"
                                    "/archive/STABLE.tar.gz",
                                    "/tmp/pma.tar.gz"]]

        if self.app.pargs.adminer:
            packages = packages + [["http://downloads.sourceforge.net/adminer"
                                    "/adminer-4.1.0.php", "/var/www/22222/"
                                    "htdocs/db/adminer/index.php"]]

        if self.app.pargs.utils:
            packages = packages + [["http://phpmemcacheadmin.googlecode.com/"
                                    "files/phpMemcachedAdmin-1.2.2"
                                    "-r262.tar.gz", '/tmp/memcache.tar.gz'],
                                   ["https://raw.githubusercontent.com/rtCamp/"
                                    "eeadmin/master/cache/nginx/clean.php",
                                    "/var/www/22222/htdocs/cache/"
                                    "nginx/clean.php"],
                                   ["https://raw.github.com/rlerdorf/opcache-"
                                    "status/master/opcache.php",
                                    "/var/www/22222/htdocs/cache/"
                                    "opcache/opcache.php"],
                                   ["https://raw.github.com/amnuts/opcache-gui"
                                    "/master/index.php",
                                    "/var/www/22222/htdocs/"
                                    "cache/opcache/opgui.php"],
                                   ["https://gist.github.com/ck-on/4959032/raw"
                                    "/0b871b345fd6cfcd6d2be030c1f33d1ad6a475cb"
                                    "/ocp.php",
                                    "/var/www/22222/htdocs/cache/"
                                    "opcache/ocp.php"],
                                   ["https://github.com/jokkedk/webgrind/"
                                    "archive/master.tar.gz",
                                    '/tmp/webgrind.tar.gz'],
                                   ["http://bazaar.launchpad.net/~percona-too"
                                    "lkit-dev/percona-toolkit/2.1/download/he"
                                    "ad:/ptquerydigest-20110624220137-or26tn4"
                                    "expb9ul2a-16/pt-query-digest",
                                    "/usr/bin/pt-query-advisor"],
                                   ["https://github.com/box/Anemometer/archive"
                                    "/master.tar.gz",
                                    '/tmp/anemometer.tar.gz']
                                   ]

        self.pre_pref(apt_packages)
        if len(apt_packages):
            pkg.update()
            pkg.install(apt_packages)
        if len(packages):
            EEDownload.download(packages)
        self.post_pref(apt_packages, packages)

    @expose()
    def remove(self):
        pkg = EEAptGet()
        apt_packages = []
        packages = []

        if self.app.pargs.web:
            apt_packages = (apt_packages + EEVariables.ee_nginx +
                            EEVariables.ee_php + EEVariables.ee_mysql)
        if self.app.pargs.admin:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.mail:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.nginx:
            apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.php:
            apt_packages = apt_packages + EEVariables.ee_php
        if self.app.pargs.mysql:
            apt_packages = apt_packages + EEVariables.ee_mysql
        if self.app.pargs.postfix:
            apt_packages = apt_packages + EEVariables.ee_postfix
        if self.app.pargs.wpcli:
            packages = packages + ['/usr/bin/wp']
        if self.app.pargs.phpmyadmin:
            packages = packages + ['/var/www/22222/htdocs/db/pma']
        if self.app.pargs.adminer:
            packages = packages + ['/var/www/22222/htdocs/db/adminer']
        if self.app.pargs.utils:
            packages = packages + ['/var/www/22222/htdocs/php/webgrind/',
                                   '/var/www/22222/htdocs/cache/opcache',
                                   '/var/www/22222/htdocs/cache/nginx/'
                                   'clean.php',
                                   '/var/www/22222/htdocs/cache/memcache',
                                   '/usr/bin/pt-query-advisor',
                                   '/var/www/22222/htdocs/db/anemometer']

        if len(apt_packages):
            pkg.remove(apt_packages)
        if len(packages):
            EEFileUtils.remove(packages)

    @expose()
    def purge(self):
        pkg = EEAptGet()
        apt_packages = []
        packages = []

        if self.app.pargs.web:
            apt_packages = (apt_packages + EEVariables.ee_nginx
                            + EEVariables.ee_php + EEVariables.ee_mysql)
        if self.app.pargs.admin:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.mail:
            pass
            # apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.nginx:
            apt_packages = apt_packages + EEVariables.ee_nginx
        if self.app.pargs.php:
            apt_packages = apt_packages + EEVariables.ee_php
        if self.app.pargs.mysql:
            apt_packages = apt_packages + EEVariables.ee_mysql
        if self.app.pargs.postfix:
            apt_packages = apt_packages + EEVariables.ee_postfix
        if self.app.pargs.wpcli:
            packages = packages + ['/usr/bin/wp']
        if self.app.pargs.phpmyadmin:
            packages = packages + ['/var/www/22222/htdocs/db/pma']
        if self.app.pargs.adminer:
            packages = packages + ['/var/www/22222/htdocs/db/adminer']
        if self.app.pargs.utils:
            packages = packages + ['/var/www/22222/htdocs/php/webgrind/',
                                   '/var/www/22222/htdocs/cache/opcache',
                                   '/var/www/22222/htdocs/cache/nginx/'
                                   'clean.php',
                                   '/var/www/22222/htdocs/cache/memcache',
                                   '/usr/bin/pt-query-advisor',
                                   '/var/www/22222/htdocs/db/anemometer'
                                   ]

        if len(apt_packages):
            pkg.remove(apt_packages, purge=True)
        if len(packages):
            EEFileUtils.remove(packages)


def load(app):
    # register the plugin class.. this only happens if the plugin is enabled
    handler.register(EEStackController)
    handler.register(EEStackStatusController)

    # register a hook (function) to run after arguments are parsed.
    hook.register('post_argument_parsing', ee_stack_hook)
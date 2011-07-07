#!/usr/bin/env python

#Skype Log Viewer: A simple http server that publishes human readable skype logs
#Copyright (C) 2011 Horacio Duran <hduran@machinalis.com>

#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.


#The SkypeLog class has been copied from http://stuffresearch.tor.hu/, the
#author of the blog gave permission to use it but claimed it is not of his
#authorship and does not know the original author, googling the code
#returns no other hit, if you are the author of this and want to be
#credited, remove the code or other changes in licencing please contact
#me at hduran at machinalis dot com

from struct import unpack
import sys, os, string, re, copy, urllib
from datetime import datetime as dt
from glob import glob
import SimpleHTTPServer, SocketServer

STATIC=['skypelogviewer.css', 'js/jquery-1.6.2.min.js', 'js/jquery.collapsible-v.1.3.0.js']

HEADER_SIZE = 8

PORT = 8699

CMD_RELOAD='reload'
CMD_SHOW='show'
CMD_MERGE='merge'
CMD_CHOOSE='choose'

BASE_HTML = open('main.html', 'r').read()
CHAT_HTML = open('chat.html', 'r').read()
HEADER_HTML = open('header.html', 'r').read()
STARTFORM_HTML = open('startform.html', 'r').read()

class SkypeLog(object):
    def __init__(self, filename, record_size):
        self.__records = []
        with open(filename, 'rb') as f:
            while True:
                data = f.read(record_size + HEADER_SIZE)
                f.flush()
                if data:
                    record = self.__read_record(data)
                    self.__records.append(record)
                else:
                    break

    def records(self):
        for record in self.__records:
            yield record

    def __read_record(self, data):
        check, length = unpack("<ii", data[:HEADER_SIZE])
        s = data[HEADER_SIZE:length]

        return {'id': self.__read_item(s, '\xE0\x03'),
                'username': self.__read_item(s, '\xE8\x03'),
                'displayname': self.__read_item(s, '\xEC\x03'),
                'message': self.__read_item(s, '\xFC\x03'),
                'timestamp': self.__timestamp(self.__read_item(s, '\xE5\x03', '\x03'))
               }

    def __read_item(self, s, start_seq, end_seq='\x00'):
        result = ""
        index = string.find(s, start_seq) + len(start_seq)
        if index != -1:
            try:
                c = s[index]
                while c != end_seq:
                    result += c
                    index += 1
                    c = s[index]
            except IndexError:
                pass
        return result

    def __timestamp(self, data):
        num = 0
        for i, d in enumerate(data):
            num |= (ord(d) & 0x7F) << (i * 7)
        return num

    def __repr__(self):
        return "<SkypeLog %d items>" & len(self.__records)

    def __len__(self):
        return len(self.__records)


class Chat(object):
    def __init__(self, record):
        #print record
        self.record_id = record['id']
        self._record_participants = copy.copy([])
        self._data = []
        super(Chat, self).__init__()
        self.add_record(record)

    @property
    def beginning(self):
        return dt.fromtimestamp(self._data[0]['timestamp'])

    @property
    def end(self):
        return dt.fromtimestamp(self._data[-1]['timestamp'])

    def add_people(self, person_name):
        if person_name not in self._record_participants:
            self._record_participants.append(person_name)

    def add_record(self, record):
        self._data.append(record)
        self.add_people(record['username'])

    @property
    def people(self):
        return self._record_participants

    @property
    def chat_id(self):
        beginning = self.beginning.strftime(u"<span class='date'>%d/%m/%Y</span> - <span class='time'>%H:%M</span>")
        chat_id = u"<span class='timestamp'>%s</span> <span class='participants'>(%s)</span>" % (beginning, ",".join(self.people))
        return chat_id

    @property
    def pretty_records(self):
        """
        We add a nickname<number> class to each message in order to be able to
        theme each line in a different way.
        """
        people_number_map = {}
        for each_people in range(0, len(self.people)):
            people_number_map[self.people[each_people]] = each_people
        for value in self._data:
            date = dt.fromtimestamp(value['timestamp'])
            date = date.strftime("%d/%m/%Y - %H:%M")
            try:
                display_name = value['displayname'].decode('utf-8')
            except UnicodeDecodeError:
                display_name = value['displayname'].decode('latin-1')
            try:
                message = value['message'].decode('utf-8')
            except UnicodeDecodeError:
                message = value['message'].decode('latin-1')
            pretty = u"""<span class='timestamp'>(%s)</span>
                         <span class='nickname nickname%d'>&lt;%s&gt;:</span>
                         <span class='message'>%s</span>""" % \
                         (date, people_number_map[value['username']], display_name, message)
            yield pretty

    def matches_search_criteria(self, search_criteria):
        """
        Let us use the any of these words criteria, if I get to shake off my
        lazyness I will add this option to the UI so the user can choose
        any or all.
        """
        for each_chat in self._data:
            for each_criteria in search_criteria.split(' '):
                if each_criteria in each_chat.get('message'):
                    return True

    def has_any_of_these_people(self, these_people):
        """
        Same as for matches
        """
        for each_people in these_people:
            if each_people in self.people:
                return True

    def __str__(self):
        return str(self.chat_id)

    def __unicode__(self):
        return unicode(self.chat_id)

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if isinstance(other, dict):
            return other.get('id', None) == self.record_id
        elif isinstance(other, self.__class__):
            return self.record_id == other.record_id

    def __cmp__(self, other):
        return cmp(self.beginning, other.beginning)

class History(object):
    def __init__(self):
        self.chats = []
        self.skype_files = None
        self.everyone = []
        super(History, self).__init__()

    def get_skype_files_options(self):
        skypefiles = glob(os.path.join(os.path.expanduser('~/.Skype'), '*'))
        skypefiles = [afile for afile in skypefiles if os.path.isdir(afile)]
        return skypefiles

    def set_skype_files_location(self, option):
        skypefiles = self.get_skype_files_options()
        if option >= len(skypefiles):
            print "la cagaste"
            sys.exit(1)
        skype_folder = skypefiles[option]
        self.skype_files = glob(skype_folder + "/chatmsg*.dbb")
        self.load_logs()

    def load_logs(self):
        self.chats = []
        self.everyone = []
        for each_logfile in self.skype_files:
            a_match = re.search(r'chatmsg(\d+).dbb$', each_logfile)
            log_size = int(a_match.group(1))
            log = SkypeLog(each_logfile, log_size)

            for record in log.records():
                if self.chats and (record == self.chats[-1]):
                    self.chats[-1].add_record(record)
                else:
                    self.chats.append(Chat(record))
        for each_chat in self.chats:
            for each_person in each_chat.people:
                if each_person not in self.everyone:
                    self.everyone.append(each_person)

        self.chats.sort()
        self.chats.reverse()

    def html_chat_index(self, search=[], filter_people=[]):
        html_output = "<ul id='chatlist'>"
        for value in  range(0, len(self.chats)):
            this_chat = self.chats[value]
            if this_chat.chat_id is None:
                continue
            if search and not this_chat.matches_search_criteria(search):
                continue
            if filter_people and not this_chat.has_any_of_these_people(filter_people):
                continue

            html_output += "<li class='chat_log'>"
            html_output += "<a class='chat_log' href='/show/%s'>%s</a>" % \
                            (value, this_chat.chat_id)
            html_output += "</li>"
        html_output += "</ul>"
        return html_output

    def format_chat_log(self, log_id):
        html_output = "<ul id='chatlog_list'>"
        for each_pretty_log in self.chats[log_id].pretty_records:
            html_output += "<li class='chatlog_line'>%s</li>" % each_pretty_log
        html_output += "</ul>"
        return html_output

HISTORY = History()

class SkypeLogHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):

    def parse_opts(self):
        """
        Parse the get options and, if present restful commands
        """
        values = dict(command=None, options={})
        if '?' in self.path:
            main, query = self.path.split("?", 1)
            value_options = dict()
            for qval in query.split('&'):
                qkey, qvalue = qval.split('=', 1)
                qvalue = urllib.unquote_plus(qvalue)
                value_options.setdefault(qkey,[]).append(qvalue)

            values['options'] = value_options
        else:
            main = self.path[1:]
        if len(main) > 1:
            chain = main.split('/')
            command = chain[0]
            values['command'] = command
            if command == CMD_SHOW:
                try:
                    values['command_opts'] = int(chain[1])
                except ValueError, err:
                    #Whatever it is is not ID-able
                    self.we_failed()
            elif command == CMD_MERGE:
                values['command_opts'] = [an_id for an_id in chain[1:]]
            elif command == CMD_CHOOSE:
                values['command_opts'] = chain[1]
        return values

    def fill_headers(self):
        #FIXME: This should use the output of parse dict and fill values
        userfilter_values = ""
        for each_user in HISTORY.everyone:
            userfilter_values += "<option value='%s'>%s</option>" % (each_user,
                                                                    each_user)
        searchbox_value=""
        return dict(userfilter_values=userfilter_values,
                    searchbox_value=searchbox_value,
                    action='/')

    def we_failed(self):
        self.send_response(500)

    def we_succeded(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()

    def do_GET(self):
        if self.path[1:] in STATIC:
            return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
        values = self.parse_opts()

        command = values['command']
        #If he have choose is that the user has chosen a user
        if command == CMD_CHOOSE:
            global HISTORY
            #We need to send 200 before processing or we timeout somtimes
            self.we_succeded()
            HISTORY.set_skype_files_location(int(values['command_opts']))

        #We need to choose a skype user first
        if not HISTORY.skype_files:
            chooseables = HISTORY.get_skype_files_options()
            response_body = ""
            for each_user in range(0, len(chooseables)):
                user = os.path.split(chooseables[each_user])[-1]
                response_body += u"""<li class="possible_user">
                                        <a href='/choose/%s'>%s
                                        </a>
                                     </li>""" % \
                                     (each_user, user)
            self.we_succeded()
            self.wfile.write(STARTFORM_HTML % {'choseable_users':response_body})
            return

        #We have been asked to reload the logas
        if command == CMD_RELOAD:
            HISTORY.load_logs()
            self.we_succeded()

        #TODO: Convert to command usage
        elif command == CMD_SHOW:
            try:
                chat_id = values['command_opts']
                current = HISTORY.chats[chat_id]
                if  chat_id <= len(HISTORY.chats):
                    chat_content = HISTORY.format_chat_log(chat_id)
                    chat_title = current.chat_id
                    chatters = ",".join(current.people)
                    response_body = CHAT_HTML % \
                                {'body':chat_content,
                                'chatters': chatters,
                                'chatid':chat_title,
                                'header': HEADER_HTML % self.fill_headers()}
                    self.we_succeded()
                    self.wfile.write(response_body.encode('utf-8'))
                    return
            except ValueError, err:
                self.we_failed()

        if not command:
            self.we_succeded()
        search = values['options'].get('searchbox', [None])[0]
        filter_people = values['options'].get('userfilter', None)

        response_body = BASE_HTML % {'body':HISTORY.html_chat_index(search=search, filter_people=filter_people),
                                    'header': HEADER_HTML % self.fill_headers()}

        self.wfile.write(response_body.encode('utf-8'))


if __name__ == '__main__':
    #Il cheapo cli
    httpd = SocketServer.TCPServer(("", PORT), SkypeLogHandler)

    print "serving at http://localhost:%s" % PORT
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()

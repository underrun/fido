#!python
#
# FIDO: Format Identifier for Digital Objects
#

import argparse, sys, re, os, io, time, zipfile, datetime
import formats

version = 'fido/0.4'
defaults = {'bufsize': 16 * io.DEFAULT_BUFFER_SIZE,
            'printmatch': "OK,{5},{1.Identifier},{1.FormatName},{6.current_filesize},{0}\n",
            'printnomatch' : "KO,{2},,{3.current_filesize},{0}\n",
            'description' : """
    Format Identification for Digital Objects (fido).
    FIDO is a command-line tool to identify the file formats of digital objects.
    It is designed for simple integration into automated work-flows.
    """,
    'epilog' : """
    Open Planets Foundation (www.openplanetsfoundation.org)
    Author: Adam Farquhar, 2010
        
    FIDO uses the UK National Archives (TNA) PRONOM File Format descriptions.
    PRONOM is available from www.tna.gov.uk/pronom.
    """
}
class Fido:
    def __init__(self, quiet=False, bufsize=None, printnomatch=None, printmatch=None):
        global defaults
        self.quiet = quiet
        self.bufsize = (defaults['bufsize'] if bufsize == None else bufsize)
        self.printmatch = (defaults['printmatch'] if printmatch == None else printmatch)
        self.printnomatch = (defaults['printnomatch'] if printnomatch == None else printnomatch)
        self.time_sigs = {'name':'Sig'}
        self.time_formats = {'name':'Format'}
        t = time.clock()
        self.formats = formats.all_formats[:]
        self.compile_signatures()
        self.t_compile = time.clock() - t
        # current_* for helpful messages on interrupt, etc
        self.current_file = ''
        self.current_filesize = 0
        self.current_format = None
        self.current_sig = None
        self.current_pat = None
        self.current_count = 0  # Count of files with attempted identifies
        
    def compile_signatures(self):
        for f in self.formats:
            for s in f.signatures:
                for b in s.bytesequences:
                    b.regex = re.compile(b.regexstring, re.DOTALL | re.MULTILINE)
    
    def print_matches(self, fullname, matches, start, end):
        count = len(matches)
        if count == 0:
            sys.stdout.write(self.printnomatch.format(fullname, datetime.datetime.now(), int(1000 * (end - start)), self))
        else:
            for (f, s) in matches:
                sys.stdout.write(self.printmatch.format(fullname, f, s, count, datetime.datetime.now(), int(1000 * (end - start)), self))
        
    def print_times(self, attr, dict):
        for (k, v) in sorted(dict.items(), key=lambda x: x[1])[0:10]:
            print "{:>6} {:>15} {:>6d}msec".format(dict['name'], getattr(k, attr)[0:15], int(v * 1000))
        
    def print_summary(self, secs, diagnose=False):
        count = self.current_count
        if not self.quiet:
            print "FIDO: Loaded    {:>6d} formats in {:>2.4f} sec".format(len(self.formats), self.t_compile)
            print "FIDO: Processed {:>6d} files in {:>6.2f} msec, {:d} files/sec".format(count, secs * 1000, int(count / secs))
            if diagnose:
                self.print_times('FormatName', self.time_formats)
                self.print_times('SignatureName', self.time_sigs)
                
    def check(self, roots, recurse=False, zip=False):
        for root in roots:
            if os.path.isfile(root):
                self.check_file_or_zip(root, zip)
            else:
                for path, unused, files in os.walk(root):
                    for f in files:
                        self.check_file_or_zip(os.path.join(path, f), zip)
                    if recurse == False:
                        break
        
    def is_zip(self, matches):
        if len(matches) == 1 and matches[0][0].Identifier == 'x-fmt/263':
            return True
        else:
            return False
    
    def check_file_or_zip(self, filename, zip=False):
        self.current_file = filename
        t0 = self.time_check_file = time.clock()
        try:
            matches = self.check_file(filename)
            self.print_matches(filename, matches, start=t0, end=time.clock())
            if zip and self.is_zip(matches):
                self.check_zipfile(os.path.dirname(filename), os.path.basename(filename), matches)
        except IOError as (errno, strerror):
            print "FIDO: Error: I/O error ({0}): {1} Path is {2}".format(errno, strerror, filename)
        
    def check_zipfile(self, path, file, matches):
        zipfullname = os.path.join(path, file)
        if zipfile.is_zipfile(zipfullname):
            with zipfile.ZipFile(zipfullname, 'r') as zip:
                for item in zip.infolist():
                    if item.file_size == 0:
                        #TODO: Find a correct test for zip items that are just directories
                        continue
                    t0 = time.clock()
                    with zip.open(item) as f:
                        zip_item_name = zipfullname + '!' + item.filename
                        self.current_file = zip_item_name
                        self.current_filesize = item.file_size
                        bofbuffer = f.read(self.bufsize)
                        if item.file_size > self.bufsize:
                            # Need to read file_size%bufsize-1 buffers, 
                            # then the remainder, then we have a full left.
                            (n, r) = divmod(item.file_size, self.bufsize)
                            for unused_i in range(1, n - 1):
                                f.read(self.bufsize)
                            f.read(r)
                            eofbuffer = f.read(self.bufsize)
                        else:
                            eofbuffer = bofbuffer
                    matches = self.check_formats(bofbuffer, eofbuffer)
                    self.print_matches(zip_item_name, matches, start=t0, end=time.clock())
                    if self.is_zip(matches):
                        #FIXME: Need to recurse into the zips
                        #self.check_zipfile(path, name, matches)
                        if not self.quiet:
                            print 'FIDO: Skipping recursive zip processing: ' + zipfullname + '!' + item.filename 
        else:
            raise Exception('Not a valid zipfile: {}'.format(zipfullname))
    
    def check_file(self, file):
        self.current_file = file
        with open(file, 'rb') as f:
            size = os.stat(file)[6]
            self.current_filesize = size
            bofbuffer = f.read(self.bufsize)
            if size > self.bufsize:
                f.seek(-self.bufsize, 2)
                eofbuffer = f.read(self.bufsize)
            else:
                eofbuffer = bofbuffer
        return self.check_formats(bofbuffer, eofbuffer)
    
    def as_good_as_any(self, f1, match_list):
        #return True
        for (f2, unused) in match_list:
            if f1 == f2:
                continue
            for (rel, fID) in getattr(f2, u'relatedformat', []):
                if rel == u'Has priority over' and fID == f1.FormatID:
                    #print (f2.FormatID, f2.Identifier, f2.FormatName), 'is better than', (f1.FormatID, f1.Identifier, f1.FormatName)
                    # Then f2 is better, so f1 is worse
                    return False
        return True
        
    def check_formats(self, bofbuffer, eofbuffer):
        # Collect matches for each format
        self.current_count += 1
        result = []
        for format in self.formats:
            self.current_format = format
            # we can prune out formats that are worse than the current match, but for every 3, well test 300, so it has to be efficient. 
            if self.as_good_as_any(format, result):
                match = self.check_format(format, bofbuffer, eofbuffer)
                if match != None:
                    result.append(match)
        # Remove any non-preferred formats
        # This is very inefficient, but doesn't happen often
        # So far, I've seen max 7, a couple of 4, 2, almost all 0 or 1 matches
        # There are few better-than me, and more worse-than me relations
        result = [(f, s) for (f, s) in result if self.as_good_as_any(f, result)]
        return result
    
    def check_format(self, format, bofbuffer, eofbuffer):
        t = time.clock()
        result = None  
        for s in format.signatures:
            self.current_sig = s
            if self.check_sig(s, bofbuffer, eofbuffer):
                # only need one match for each format
                result = (format, s)
                break
        self.time_formats[format] = time.clock() - t + self.time_formats.get(format, 0.0)
        return result
    
    def check_sig(self, sig, bofbuffer, eofbuffer):
        match = True
        t = time.clock()
        for b in sig.bytesequences:
            #print "try", sig.SignatureName, b.PositionType, b.regexstring
            self.current_pat = b
            t_beg = time.clock()
            if 'BOF' in b.PositionType:
                if not re.match(b.regex, bofbuffer):
                    return False
            elif 'EOF' in b.PositionType:
                if not re.match(b.regex, eofbuffer):
                    return False
            elif 'Variable' in b.PositionType:
                if not re.search(b.regex, bofbuffer):
                    match = False
            else:
                raise Exception("bad positionType")
            t_end = time.clock()
            if t_end - t_beg > 0.05:
                print "FIDO: Slow sig {}s {1.SignatureName} {2.regexstring}".format(t_end - t_beg, sig, b)
        # Should fall through to here if everything matched
        self.time_sigs[sig] = time.clock() - t + self.time_sigs.get(sig, 0.0)
        return match

def main(arglist=None):
    if arglist == None:
        arglist = sys.argv[1:]
    parser = argparse.ArgumentParser(description=defaults['description'], epilog=defaults['epilog'])
    parser.add_argument('-v', default=False, action='store_true', help='show version information')
    parser.add_argument('-q', default=False, action='store_true', help='run (more) quietly')
    parser.add_argument('-bufsize', type=int, default=None, help='size of the buffer to match against')
    parser.add_argument('-recurse', default=False, action='store_true', help='recurse into subdirectories')
    parser.add_argument('-zip', default=False, action='store_true', help='recurse into zip files')
    parser.add_argument('-diagnose', default=False, action='store_true', help='show some diagnostic information')
    parser.add_argument('-matchprintf', metavar='FORMATSTRING', default=None, help='format string (Python style) to use on match. {0}=path, {1}=format object, {2}=signature, {3}=match count, {4}=now.')
    parser.add_argument('-nomatchprintf', metavar='FORMATSTRING', default=None, help='format string (Python style) to use if no match. {0}=path, {1}=now.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-input', default=False, help='file containing a list of files to check, one per line')
    group.add_argument('files', nargs='*', default=[], metavar='FILE', help='files to check')
        
    args = parser.parse_args(arglist)
        
    if args.v :
        print version
        exit(1)
        
    fido = Fido(quiet=args.q, bufsize=args.bufsize, printmatch=args.matchprintf, printnomatch=args.nomatchprintf)
    if args.input != False:
        args.files = [os.path.normpath(line[:-1]) for line in open(args.input, 'r').readlines()]
    else:
        args.files = [os.path.normpath(line) for line in args.files]
    #print args.files
    t0 = time.clock()
    try:
        fido.check(args.files, recurse=args.recurse, zip=args.zip)
    except KeyboardInterrupt:
        try:
            print "FIDO: Interrupt during:\n  File: {0}\n  Format: Puid={1.Identifier} [{1.FormatName}]\n  Sig: ID={2.SignatureID} [{2.SignatureName}]\n  Pat={3.ByteSequenceID} {3.regexstring!r}".format(fido.current_file, fido.current_format,
                                                       fido.current_sig, fido.current_pat)
        except AttributeError:
            # the things may not be set yet.
            print "FIDO: Aborted during: File: {}".format(fido.current_file)
        raise
    t1 = time.clock()
    if not args.q:
        fido.print_summary(t1 - t0, args.diagnose)
       
if __name__ == '__main__':
    #main(['-r', r'e:\Code\fidotests\corpus\Buckland -- Concepts of Library Goodness.htm' ])
    #check(r'e:\Code\fidotests',True,True)
    #main(['-r', '-b 3000', r'e:/Code/fidotests/corpus/b.ppt'])
    #main(['-r', '-z', r'e:/Code/fidotests/corpus/'])
    #main(['-r',r'c:/Documents and Settings/afarquha/My Documents'])
    #main(['-r', r'c:\Documents and Settings\afarquha\My Documents\Proposals'])
    main(['-h'])
    main()
    

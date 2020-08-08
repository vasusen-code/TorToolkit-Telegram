import qbittorrentapi as qba
import asyncio as aio
import os
import logging,traceback
from datetime import datetime,timedelta
from tortoolkit.functions import Hash_Fetch
from tortoolkit.functions.Human_Format import human_readable_bytes,human_readable_timedelta 
from tortoolkit.core.getVars import get_val
from telethon.tl.types import KeyboardButtonCallback

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('qbittorrentapi').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

async def get_client(host=None,port=None,uname=None,passw=None,retry=2):
    """Creats and returns a client to communicate with qBittorrent server. Max Retries 2
    """
    #getting the conn 
    host = host if host is not None else "localhost"
    port = port if port is not None else "8080"
    uname = uname if uname is not None else "admin"
    passw = passw if passw is not None else "adminadmin"
    logging.info(f"Trying to login in qBittorrent using creds {host} {port} {uname} {passw}")

    client = qba.Client(host=host,port=port,username=uname,password=passw)
    
    #try to connect to the server :)
    try:
        client.auth_log_in()
        logging.info("Client connected successfully to the torrent server. :)")
        return client
    except qba.LoginFailed as e:
        logging.error("An errot occured invalid creds detected\n{}\n{}".format(e,traceback.format_exc()))
        return None
    except qba.APIConnectionError:
        if retry == 0:
            logging.error("Tried to get the client 3 times no luck")
            return None
        
        logging.info("Oddly enough the qbittorrent server is not running.... Attempting to start at port {}".format(port))
        cmd = f"qbittorrent-nox -d --webui-port={port}"
        cmd = cmd.split(" ")

        subpr = await aio.create_subprocess_exec(*cmd,stderr=aio.subprocess.PIPE,stdout=aio.subprocess.PIPE)
        out, err = await subpr.communicate()
        return await get_client(host,port,uname,passw,retry=retry-1)


async def add_torrent_magnet(magnet,message):
    """Adds a torrent by its magnet link.
    """
    client = await get_client()
    try:
        ctor = len(client.torrents_info())
        op = client.torrents_add(magnet)
        ext_hash = Hash_Fetch.get_hash_magnet(magnet)
        #this method dosent return anything so have to work around
        if op.lower() == "ok.":
            st = datetime.now()
            
            ext_res = client.torrents_info(torrent_hashes=ext_hash)
            if len(ext_res) > 0:
                logging.info("Got torrent info from ext hash.")
                return ext_res[0]

            while True:
                if (datetime.now() - st).seconds >= 10:
                    logging.warning("The provided torrent was not added and it was timed out. magnet was:- {}".format(magnet))
                    await message.edit("The torrent was not added due to an error.")
                    return False
                ctor_new = client.torrents_info()
                if len(ctor_new) > ctor:
                    return ctor_new[0]

        else:
            await message.edit("This is an unsupported/invalid link.")
    except qba.UnsupportedMediaType415Error as e:
        #will not be used ever ;)
        logging.error("Unsupported file was detected in the magnet here")
        await message.edit("This is an unsupported/invalid link.")
        return False
    except Exception as e:
        logging.error("{}\n{}".format(e,traceback.format_exc()))
        await message.edit("Error occured check logs.")
        return False

async def add_torrent_file(path,message):
    if not os.path.exists(path):
        logging.error("The path supplied to the torrent file was invalid.\n path:-{}".format(path))
        return False

    client = await get_client()
    try:
        ctor = len(client.torrents_info())
        op = client.torrents_add(torrent_files=[path])
        #this method dosent return anything so have to work around
        ext_hash = Hash_Fetch.get_hash_file(path)
        if op.lower() == "ok.":
            st = datetime.now()
            #ayehi wait karna hai
            aio.sleep(2)
            
            ext_res = client.torrents_info(torrent_hashes=ext_hash)
            if len(ext_res) > 0:
                logging.info("Got torrent info from ext hash.")
                return ext_res[0]

            while True:
                if (datetime.now() - st).seconds >= 20:
                    logging.warning("The provided torrent was not added and it was timed out. file path was:- {}".format(path))
                    await message.edit("The torrent was not added due to an error.")
                    return False
                ctor_new = client.torrents_info()
                if len(ctor_new) > ctor:
                    return ctor_new[0]

        else:
            await message.edit("This is an unsupported/invalid link.")
    except qba.UnsupportedMediaType415Error as e:
        #will not be used ever ;)
        logging.error("Unsupported file was detected in the magnet here")
        await message.edit("This is an unsupported/invalid link.")
        return False
    except Exception as e:
        logging.error("{}\n{}".format(e,traceback.format_exc()))
        await message.edit("Error occured check logs.")
        return False

async def update_progress(client,message,torrent,except_retry=0):
    tor_info = client.torrents_info(torrent_hashes=torrent.hash)
    
    #update cancellation
    if len(tor_info) > 0:
        tor_info = tor_info[0]
    else:
        await message.edit("Torrent canceled ```{}``` ".format(torrent.name),buttons=None)
        return True
    
    try:
        msg = "<b>Downloading:</b> <code>{}</code>\n".format(
            tor_info.name
            )
        msg += "<b>Down:</b> {} <b>Up:</b> {}\n".format(
            human_readable_bytes(tor_info.dlspeed,postfix="/s"),
            human_readable_bytes(tor_info.upspeed,postfix="/s")
            )
        msg += "<b>Progress:</b> {} - {}%\n".format(
            progress_bar(tor_info.progress),
            round(tor_info.progress*100,2)
            )
        msg += "<b>Downloaded:</b> {} of {}\n".format(
            human_readable_bytes(tor_info.downloaded),
            human_readable_bytes(tor_info.total_size)
            )
        msg += "<b>ETA:</b> <b>{} Mins</b>\n".format(
            human_readable_timedelta(tor_info.eta)
            )
        msg += "<b>S:</b>{} <b>L:</b>{}\n".format(
            tor_info.num_seeds,tor_info.num_leechs
            )
        msg += "<b>Using engine:</b> <code>qBittorrent</code>"
        
        #error condition
        if tor_info.state == "error":
            await message.edit("Torrent <code>{}</code> errored out.",buttons=message.reply_markup,parse_mode="html")
            logging.error("An torrent has error clearing that torrent now. Torrent:- {} - {}".format(tor_info.hash,tor_info.name))
            return False
        #stalled
        if tor_info.state == "stalledDL":
            await message.edit("Torrent <code>{}</code> is stalled(waiting for connection) temporarily.".format(tor_info.name),buttons=message.reply_markup,parse_mode="html")
        #meta stage
        if tor_info.state == "metaDL":
            await message.edit("Getting metadata for {} - {}".format(tor_info.name,datetime.now().strftime("%H:%M:%S")),buttons=message.reply_markup)
        elif tor_info.state == "downloading" or tor_info.state.lower().endswith("dl"):
            await message.edit(msg,parse_mode="html",buttons=message.reply_markup) 

        #aio timeout have to switch to global something
        await aio.sleep(get_val("EDIT_SLEEP_SECS"))

        #stop the download when download complete
        if tor_info.state == "uploading" or tor_info.state.lower().endswith("up"):
            client.torrents_pause(tor_info.hash)
            await message.edit("Download completed ```{}```. To path ```{}```".format(tor_info.name,tor_info.save_path),buttons=None)
            return os.path.join(tor_info.save_path,tor_info.name)
        else:
            return await update_progress(client,message,torrent)
    except Exception as e:
        await message.edit("Error occure {}".format(e),buttons=None)
        logging.error("{}\n\n{}\n\nn{}".format(e,traceback.format_exc(),tor_info))
        return False



def progress_bar(percentage):
    """Returns a progress bar for download
    """
    #percentage is on the scale of 0-1
    comp = "▰"
    ncomp = "▱"
    pr = ""

    for i in range(1,11):
        if i <= int(percentage*10):
            pr += comp
        else:
            pr += ncomp
    return pr

async def deregister_torrent(hashid):
    client = await get_client()
    client.torrents_delete(torrent_hashes=hashid,delete_files=True)

async def register_torrent(entity,message,magnet=False,file=False):
    client = await get_client()
    if magnet:
        torrent = await add_torrent_magnet(entity,message)
        if torrent.progress == 1:
            await message.edit("The provided torrent was already completly downloaded.")
            return True
        else:
            data = "torcancel {}".format(torrent.hash)
            message = await message.edit(buttons=[[KeyboardButtonCallback("Cancel Leech",data=data.encode("UTF-8"))]])
            return await update_progress(client,message,torrent)
    if file:
        torrent = await add_torrent_file(entity,message)
        if torrent.progress == 1:
            await message.edit("The provided torrent was already completly downloaded.")
            return True
        else:
            data = "torcancel {}".format(torrent.hash)
            message = await message.edit(buttons=[[KeyboardButtonCallback("Cancel Leech",data=data.encode("UTF-8"))]])
            return await update_progress(client,message,torrent)
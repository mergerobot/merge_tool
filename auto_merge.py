#!/usr/bin/python3
'''
Auto Merge
'''

import os
import argparse
import configparser
import logging
import subprocess
import tempfile
from pathlib import Path
import shutil
import re

WORKDIR = tempfile.TemporaryDirectory()
DEF_CACHE_DIR = "/tmp/mergerobot.cache"
CONFIG_ITEMS = ["src",
                "src_branch",
                "src_user",
                "src_token",
                "src_rev",
                "tgt",
                "tgt_user",
                "tgt_branch",
                "tgt_token",
                "enabled"
               ]
                  

#class WORKDIR:
#  name = "/tmp/tmpmb_helfd.keep"
def run_cmd(cmd, timeout=30, outf=None):
    '''
    run subprocess, return CompletedProcess object
    return code is in result.returncode
    '''
    logging.debug("Run_cmd : { " + (" ").join(cmd) + " }")
    if outf is not None:
      outfp = open(outf, "w")
    else:
      outfp = subprocess.PIPE
    try :
      result = subprocess.run(cmd, stdout=outfp, stderr=subprocess.PIPE, timeout=timeout)
      if result.returncode != 0 :
        logging.error("Error: Exec Failed - { " + (" ").join(cmd) + " }\n" + 
                       result.stdout.decode("utf-8") + "\n" + 
                       result.stderr.decode("utf-8"))
    except Exception as e:
        result = subprocess.CompletedProcess(cmd, 1)
        logging.error("Exec cmd Failed with exception: { " + (" ").join(cmd) + " } :" + str(e))
    return result


def get_full_link(repo, user, pwd):
    '''
    get full repo link with username and passwd
    '''
    if user != '':
        user = user.replace("@", "%40")
        link_prefix = user
        if pwd != '':
            link_prefix = link_prefix + ":" + pwd
        link_prefix += "@"
        src_full = repo.replace("//", "//" + link_prefix, 1)
    else :
        src_full = repo
    return src_full

def process_config(merge_config):
    logging.debug("[process_config]")
    for config_item in CONFIG_ITEMS:
        if config_item not in merge_config:
            if config_item in global_config:
                merge_config[config_item] = global_config[config_item]
            elif config_item == "enabled":
                # default enabled
                merge_config["enabled"] = "True"
            else:
                logging.error("@@Error: missing config " + config_item)
                return 1
        

    merge_config['src_full_link'] = get_full_link(merge_config['src'],
                                                 merge_config['src_user'],
                                                 merge_config['src_token'])
    merge_config['tgt_full_link'] = get_full_link(merge_config['tgt'],
                                                 merge_config['tgt_user'],
                                                 merge_config['tgt_token'])
    if re.search("^[0-9a-z]*...[0-9a-z]*$", merge_config['src_rev']) is None:
        logging.error("@@Error: src_rev: " + merge_config['src_rev'] + " not a valid revision range") 
        return 1
    return 0

def test_git_connection(gitconfig):
    '''
    Test Git connection
    '''
    logging.debug("[tet_git_connection]")
    src_testcmd = ['git', 'ls-remote', '-h', gitconfig['src_full_link'], '-b', gitconfig['src_branch'] ]
    src_res = run_cmd(src_testcmd).returncode
    if src_res == 0:
        logging.info("@@Git Source Connection SUCCESS")
    else:
        logging.info("@@Git Source Connection FAILED")

    tgt_testcmd = ['git', 'ls-remote', '-h', gitconfig['tgt_full_link'], '-b', gitconfig['tgt_branch'] ]
    tgt_res = run_cmd(tgt_testcmd).returncode
    if tgt_res == 0:
        logging.info("@@Git Target Connection SUCCESS")
    else:
        logging.info("@@Git Target Connection FAILED")

    return src_res or tgt_res

def get_workdir_name(repo_name):
    return "merge_" + repo_name  + ".workdir"

def copy_from_cache(merge_item, merge_link, merge_dir, branch):
    logging.debug("[copy_from_cache]")
    ret = False
    olddir = os.getcwd()
    cached_dir = args.cache_dir + "/" + get_workdir_name(merge_item)
    if os.path.exists(cached_dir) :
        for item in os.listdir(cached_dir):
            item_dir = cached_dir + "/" + item
            os.chdir(item_dir)
            run_result = run_cmd(['git', 'remote', 'get-url', 'origin'], 10)
            url = run_result.stdout.decode('utf-8').replace('\n', '')
            if run_result.returncode == 0 and url == merge_link:
               # cache exists
               dirname = os.path.dirname(merge_dir)
               if os.path.exists(merge_dir) :
                   logging.error(merge_dir + " already exists")
                   break
               if run_cmd(['cp', '-r', item_dir, dirname], 60).returncode == 0:
                   os.chdir(merge_dir)
                   cur_branch = run_cmd(['git', 'branch', '--show-current'])\
                                        .stdout.decode('utf-8').replace('\n', '')
                   if cur_branch != branch:
                       if run_cmd(['git', 'checkout', branch, '&&', 'git', 'pull']).returncode != 0:
                           break
                   ret = True
                   break
            else:
                continue
        
    os.chdir(olddir) 
    return ret

def save_to_cache(merge_item, merge_dir):
    logging.debug("[save_to_cache]")
    ret = False
    olddir = os.getcwd()
    cached_dir = args.cache_dir + "/" + get_workdir_name(merge_item)
    if not os.path.exists(cached_dir):
        os.mkdir(cached_dir)
    if run_cmd(['cp', '-r', merge_dir, cached_dir], 100).returncode == 0:
        ret = True

    os.chdir(olddir)
    return ret
    
def clone_repo(gitconfig):
    logging.debug("[clone_repo]")
    src_dir = gitconfig['merge_dir'] + "/" + "merge_src"
    tgt_dir = gitconfig['merge_dir'] + "/" + "merge_tgt"
    ret = copy_from_cache(gitconfig['merge_item'], gitconfig['src_full_link'], src_dir, gitconfig['src_branch'])
    if ret is False:
        clone_src_cmd = ['git', 'clone', gitconfig['src_full_link'], '-b', gitconfig['src_branch'], "merge_src" ]
        src_res = run_cmd(clone_src_cmd, 1000).returncode
        if src_res == 0 :
            save_to_cache(gitconfig['merge_item'], src_dir)
            logging.info("@@Clone Source Success ")
        else :
            logging.info("@@Clone Source Failed ")
    else :
        logging.info("@@Clone Source From Cache Success ")
        src_res = 0

    ret = copy_from_cache(gitconfig['merge_item'], gitconfig['tgt_full_link'], tgt_dir, gitconfig['tgt_branch'])
    if ret is False:
        clone_tgt_cmd = ['git', 'clone', gitconfig['tgt_full_link'], '-b', gitconfig['tgt_branch'], "merge_tgt" ]
        tgt_res = run_cmd(clone_tgt_cmd, 1000).returncode
        if tgt_res == 0 :
            save_to_cache(gitconfig['merge_item'], tgt_dir)
            logging.info("@@Clone Target Success ")
        else :
            logging.info("@@Clone Target Failed ")
    else :
        tgt_res = 0
        logging.info("@@Clone Target From Cache Success ")

    return src_res or tgt_res

def make_patches(gitconfig):
    logging.debug("[make_patches]")
    if not os.path.exists("merge_src"):
        logging.error("Cloned source merge_src does not exists in " + os.getcwd())
        return 1
    os.chdir("merge_src")

    # make patches from source repo with configed revison ranges 
    patch_dir = os.path.abspath("../patches")
    if os.path.exists(patch_dir):
        shutil.rmtree(patch_dir)
    patch_cmd = ['git', 'format-patch', gitconfig['src_rev'], '-o', patch_dir]
    ret = run_cmd(patch_cmd).returncode
    if ret != 0 :
        return ret
    patch_cnt = len(os.listdir(patch_dir))
    if patch_cnt == 0:
        logging.info("@@Error:None patches generated at revision range: " + gitconfig['src_rev'])
        return 1
    logging.info("@@Patches generated at: " + patch_dir)

    # filter commit messages
    patch_filtdir=os.path.abspath("../patches_filt")
    if os.path.exists(patch_filtdir):
        shutil.rmtree(patch_filtdir)
    ret = run_cmd(['cp', '-r', patch_dir, patch_filtdir]).returncode
    if ret != 0:
        return ret

    filter_cmd = ['sed', '-i', 's/^From:.*/From: mergerobot <>/']
    for patch in os.listdir(patch_filtdir):
        if patch.endswith(".patch"):
            filtf = patch_filtdir + "/" + patch
            filter_cmd.append(filtf)
    ret = run_cmd(filter_cmd, 100).returncode
    if ret != 0:
        return ret
    logging.info("@@Patches with filting generated at: " + patch_filtdir)
    return 0

def apply_patches(merge_config):
    logging.debug("[apply_patches]")
    os.chdir(merge_config['merge_dir'])
    ret = 0
    if not os.path.exists("merge_tgt"):
        logging.error("Cloned target merge_tgt does not exists in " + os.getcwd())
        return 1
    os.chdir("merge_tgt")

    apply_cmd = ['git', 'am']
    for patch in sorted(os.listdir("../patches_filt")):
        apply_cmd.append("../patches_filt/" + patch)
    ret = run_cmd(apply_cmd).returncode
    if ret == 0 :
        logging.info("@@Patches applied successfully")
    else:
        logging.info("@@Patches applied failed")
        run_cmd(['git', 'am', '--abort'])

    return ret 

def push_patches(merge_config):
    logging.debug("[push_patches]")
    ret = 0
    push_cmd = ['git', 'push']
    ret = run_cmd(push_cmd, 100).returncode
    if ret == 0 :
        logging.info("@@Push Success")
    else :
        logging.info("@@Push Failed") 
    return ret
    
def do_merge(merge_config):
    logging.debug("[do_merge]")
    for key in merge_config :
        logging.debug(key + " = " + merge_config[key])
    logging.debug("")
    ret = 0
    # test git connections
    # ret = test_git_connection(merge_config)
    if ret != 0:
        return ret
    # clone repos
    ret = clone_repo(merge_config)
    if ret != 0:
       return ret
   
    # make patches
    ret = make_patches(merge_config)
    if ret != 0:
        return ret

    # apply patches
    ret = apply_patches(merge_config)
    if ret != 0:
        args.Keep = True
        return ret

    # push patches
    ret = push_patches(merge_config)
    if ret != 0:
        args.Keep = True
        return ret
    return ret

def main():
    '''
    Main Entry
    '''
    parser = argparse.ArgumentParser(description='Run Auto Merge')
    parser.add_argument('-d', '--debug', action='store_true', default=False,
                        help='Debug mode')

    parser.add_argument('-k', '--keep', action='store_true', default=False,
                        help='Keep working dir')
    parser.add_argument('-c', '--cache_dir', default=DEF_CACHE_DIR, help='Cache dir location')
    parser.add_argument('--config', required=True, help='Config File')
    global args
    args = parser.parse_args()
    
    if args.debug is True:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO
    logformat = "%(message)s"
    logging.basicConfig(level=loglevel, format=logformat)

    if args.config is not None:
        config = configparser.RawConfigParser()
        config.read_file(open(args.config))

    logging.info("Working Dir at: " + WORKDIR.name)

    for item in config.sections() :
       if item == "global_config":
           global global_config
           global_config = dict(config.items(item))
           continue

       merge_config = dict(config.items(item))
       logging.info("================Processing merge " + item + "===============")
       if process_config(merge_config) != 0:
          continue 

       if merge_config['enabled'] == "False" :
           logging.info("Merge " + item + " is not enabled")
           continue


       merge_dir = os.path.abspath(WORKDIR.name + "/" + get_workdir_name(item))
       if not os.path.exists(merge_dir) :
           os.mkdir(merge_dir)
       os.chdir(merge_dir)
       merge_config['merge_item'] = item
       merge_config['merge_dir'] = merge_dir

       if do_merge(merge_config) != 0 :
           logging.info("@@Merge Failed: please double check error message or handy resolve in saved area")
       else:
           logging.info("@@Merge Success")

       if args.keep is True:
           logging.info("Saved Working Dir at:" + WORKDIR.name + ".keep")
           os.rename(WORKDIR.name, WORKDIR.name + ".keep")
 
if __name__ == "__main__":
   main()
    

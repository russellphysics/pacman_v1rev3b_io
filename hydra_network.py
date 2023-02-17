import larpix
import larpix.io
import time
import argparse
import graphs
import numpy as np

_default_verbose=False

_io_group_=1
_iterations_=1e3
_root_chip_ids_=[11,41,71,101]
_timeout_=0.01
_connection_delay_=0.01


def power_on_reset(c, io):
    io.set_reg(0x2014, 0xffffffff, io_group=_io_group_) # disable trigger forwarding
    io.set_reg(0x18, 0xffffffff, io_group=_io_group_) # enable pacman uart
    io.double_send_packets=False

    io.set_reg(0x14, 1, io_group=_io_group_) #enable global power
    io.reset_larpix(length=100000000,io_group=_io_group_) # 10-second hard reset
    start=time.time()
    vdda_reg=[0x00024130, 0x00024132, 0x00024134, 0x00024136, \
              0x00024138, 0x0002413a, 0x0002413c, 0x0002413e]
    vddd_reg=[0x00024131, 0x00024133, 0x00024135, 0x00024137, \
              0x00024139, 0x0002413b, 0x0002413d, 0x0002413f]
    vdda_dac=0 #46020
    for reg in vdda_reg: io.set_reg(reg, vdda_dac, io_group=_io_group_)
    vddd_dac=40605
    for reg in vddd_reg: io.set_reg(reg, vddd_dac, io_group=_io_group_)
    enable_val=[0b1000000001, 0b1000000011, 0b1000000111, 0b1000001111,
                0b1000011111, 0b1000111111, 0b1001111111, 0b1011111111]
    for val in enable_val: io.set_reg(0x10, val, io_group=_io_group_); time.sleep(1) # enable tile power
    io.set_reg(0x101c, 4, io_group=_io_group_) # enable clock
    time.sleep(2)
    print('ready ',time.time()-start,' seconds since hard reset initiated')

    io.reset_larpix(length=1024,io_group=_io_group_) # 100-microsecond hard reset
    time.sleep(0.2)

    
def setup_root_chip(c, io_group, io_channel, chip_id):
    setup_key=larpix.key.Key(io_group, io_channel, 1)
    c.add_chip(setup_key)
    c[setup_key].config.chip_id = chip_id
    c.write_configuration(setup_key, 'chip_id')
    c.remove_chip(setup_key)

    chip_key=larpix.key.Key(io_group, io_channel, chip_id)
    c.add_chip(chip_key)
    c[chip_key].config.chip_id = chip_id

    c[chip_key].config.enable_mosi=[0,1,0,0] # enable MOSI to pacman alone
    c.write_configuration(chip_key, 'enable_mosi')

    c[chip_key].config.enable_miso_upstream=[0]*4
    c.write_configuration(chip_key,'enable_miso_upstream')
    c[chip_key].config.enable_miso_downstream=[1,0,0,0]
    c.write_configuration(chip_key,'enable_miso_downstream')
    c[chip_key].config.enable_miso_differential=[1,0,0,0]
    c.write_configuration(chip_key,'enable_miso_differential')

    c[chip_key].config.clk_ctrl=1
    c.write_configuration(chip_key, 'clk_ctrl')
        
    return chip_key


def reconcile_software_to_asic(c, chip_key, verbose):
    chip_key_registers=[(chip_key, i) \
                        for i in range(c[chip_key].config.num_registers)]
    ok, diff = c.enforce_registers(chip_key_registers, timeout=_timeout_,\
                                   connection_delay=_connection_delay_,\
                                   n=5, n_verify=5)
    if verbose and not ok: print(chip_key,' FAILED CONFIGURATION') #debug
    return ok


def enable_logger(c, reconcile=True, file_prefix=None):
    now=time.strftime("%Y_%m_%d_%H_%M_%S_%Z")
    if reconcile==True:
        if file_prefix!=None: fname=file_prefix+'-reconcile-'+now+'.h5'
        else: fname='reconcile-'+now+'.h5'
    else:
        if file_prefix!=None: fname=file_prefix+'-readback-'+now+'.h5'
        else: fname='readback-'+now+'.h5'
    c.logger = larpix.logger.HDF5Logger(filename=fname)
    print('filename: ', c.logger.filename)
    c.logger.enable()
    return c.logger


def disable_logger(logger):
    logger.flush()
    logger.disable()


def pacman_io_channels():
    ctr=0; io_channels=[]; temp=[]
    for i in range(1,33,1):
        ctr+=1; temp.append(i)
        if ctr==4: io_channels.append(temp); temp=[]; ctr=0
    return io_channels


def io_channel_to_tile(io_channel):
    return int(np.floor((io_channel-1-((io_channel-1)%4))/4+1))


def set_pacman_transmit_clock(io, io_channels, divisor):
    for tile in range(len(io_channels)):
        for ioc in io_channels[tile]:
            io.set_uart_clock_ratio(ioc, divisor, io_group=_io_group_)


def setup_graphs_class():
    arr1 = graphs.NumberedArrangement(); arr2 = graphs.NumberedArrangement()
    arr3 = graphs.NumberedArrangement(); arr4 = graphs.NumberedArrangement()
    arr5 = graphs.NumberedArrangement(); arr6 = graphs.NumberedArrangement()
    arr7 = graphs.NumberedArrangement(); arr8 = graphs.NumberedArrangement()
    arr1.clear(); arr2.clear(); arr3.clear(); arr4.clear()
    arr5.clear(); arr6.clear(); arr7.clear(); arr8.clear()
    tile_graphs={1:arr1, 2:arr2, 3:arr3, 4:arr4,
                 5:arr5, 6:arr6, 7:arr7, 8:arr8}
    return tile_graphs


def reverse_traverse_larpix_transmit_clock(c, ds_network, clk_ctrl):
    for depth in range(100):
        valid_depth=False
        chip_clk_ctrl=[]
        for chip_keys in ds_network.values():
#            print('IO CHAIN LENGTH: ',len(chip_keys))
#            print('NETWORK DEPTH: ',depth)
            if len(chip_keys)-1>=depth:
                valid_depth=True
                regs=[]
                reg_map = c[chip_keys[depth]].config.register_map
                regs+=list(reg_map['clk_ctrl'])
                c[chip_keys[depth]].config.clk_ctrl=clk_ctrl
                for reg in regs:
                    chip_clk_ctrl.append( (chip_keys[depth], reg) )                
        if valid_depth==True:
            for i in range(3): c.multi_write_configuration(chip_clk_ctrl)
        if valid_depth==False:
            break
        

def set_larpix_transmit_clock(c, reverse_chain, clk_ctrl, omit_initial):
    for chip_key in reverse_chain.keys():
        ctr=0
        for ck in reverse_chain[chip_key]:
            if omit_initial==True and ctr==0:
                ctr+=1
                continue
            c[ck].config.clk_ctrl=clk_ctrl
            for i in range(3): c.write_configuration(ck, 'clk_ctrl')
#            print(ck,' set to clk_ctrl ',clk_ctrl) # debug
            

                
def configure_chip_id(c, child_chips):
    child_temp_key=[]
    for i in range(len(child_chips)):
        temp_key=larpix.key.Key(child_chips[i].io_group, child_chips[i].io_channel,1)
        c.add_chip(temp_key)
        regs=[]
        reg_map = c[temp_key].config.register_map
        regs+=list(reg_map['chip_id'])
        for reg in regs: child_temp_key.append( (temp_key, reg) )
        c[temp_key].config.chip_id=child_chips[i].chip_id
    c.multi_write_configuration(child_temp_key, connection_delay=_connection_delay_)
    for ctk in child_temp_key: c.remove_chip(ctk[0])
    for ck in child_chips:
        c.add_chip(ck)
        c[ck].config.chip_id = ck.chip_id

        
def setup_origin_chips(c, child_chips):
    configure_chip_id(c, child_chips)
    child_rx_tx=[]
    for i in range(len(child_chips)):
        c[child_chips[i]].config.enable_mosi=[1]*4 #[0,1,0,0]
        c[child_chips[i]].config.enable_miso_downstream=[1,0,0,0]
        c[child_chips[i]].config.enable_miso_upstream=[0]*4
        c[child_chips[i]].config.enable_miso_differential=[1]*4 #[1,0,0,0]
        regs=[]
        reg_map = c[child_chips[i]].config.register_map
        regs+=list(reg_map['enable_mosi'])+list(reg_map['enable_miso_downstream'])+list(reg_map['enable_miso_upstream'])+list(reg_map['enable_miso_downstream'])
        for reg in regs: child_rx_tx.append( (child_chips[i], reg) )
    c.multi_write_configuration(child_rx_tx, connection_delay=_connection_delay_)
#    ok = reconcile_software_to_asic(c, child_chips[0]) # debug
    #print('!!!!!!!debug!!!!!!!! ', ok) # debug
    
    
def setup_added_chips(c, tile_graphs, parent_chips, child_chips):
    parent_piso_us=[]
    for i in range(len(parent_chips)):
        tile=io_channel_to_tile(parent_chips[i].io_channel)
        miso_us=tile_graphs[tile].get_uart_enable_list(parent_chips[i].chip_id,
                                                       child_chips[i].chip_id)
#        print('PARENT: ',parent_chips[i],' CHILD: ',child_chips[i],' MISO US: ',miso_us) # debug
        c[parent_chips[i]].config.enable_miso_upstream=miso_us
        regs=[]
        reg_map = c[parent_chips[i]].config.register_map
        regs+=list(reg_map['enable_miso_upstream'])
        for reg in regs: parent_piso_us.append( (parent_chips[i], reg) )
    c.multi_write_configuration(parent_piso_us, connection_delay=_connection_delay_)
#    ok = reconcile_software_to_asic(c, parent_chips[0]) # debug
#    print('!!!!!!!debug!!!!!!!! ', ok) # debug
    
    configure_chip_id(c, child_chips)

    child_tx=[]
    for i in range(len(child_chips)):
        tile=io_channel_to_tile(child_chips[i].io_channel)
        miso_ds=tile_graphs[tile].get_uart_enable_list(child_chips[i].chip_id,
                                                       parent_chips[i].chip_id)
#        print('PARENT: ',parent_chips[i],' CHILD: ',child_chips[i],' MISO DS: ',miso_ds) # debug
        c[child_chips[i]].config.enable_miso_downstream=miso_ds
        c[child_chips[i]].config.enable_miso_upstream=[0]*4
        c[child_chips[i]].config.enable_miso_differential=[1]*4 # miso_ds
        regs=[]
        reg_map=c[child_chips[i]].config.register_map
        regs+=list(reg_map['enable_miso_downstream'])+list(reg_map['enable_miso_upstream'])+list(reg_map['enable_miso_differential'])
        for reg in regs: child_tx.append( (child_chips[i], reg) )
    c.multi_write_configuration(child_tx, connection_delay=_connection_delay_)
#    ok = reconcile_software_to_asic(c, child_chips[0]) # debug
#    print('!!!!!!!debug!!!!!!!! ', ok) # debug
    

def downstream_network(c, anode_paths, io_group, io_channels):
    downstream_network={}
    for ipaths, paths in enumerate(anode_paths): # ipaths+1=tile, paths=[[chip ID]]
        for ip, p in enumerate(paths):
            ioc=io_channels[ipaths][ip]
            if ioc not in downstream_network: downstream_network[ioc]=[]
            for cid in reversed(p):
                key = larpix.key.Key(io_group, ioc, cid)
                if key not in c.chips: continue
                downstream_network[ioc].append(key)
    return downstream_network

    
def chips_by_network_depth(network_depth, anode_paths, io_group, active_io_channels, io_channels):
    # for io channels 'still stepping' find all chips at depth n
    child_chips, parent_chips = [], []
    #reverse_chain={}
    chip_at_depth=False
    #print('active io channels: ',active_io_channels) # debug
    for ipaths, paths in enumerate(anode_paths): # ipaths+1==tile, paths=[[chip ID]]
        if ipaths>7: print('IPATHS>7 PATH: ',paths)
        for ip, p in enumerate(paths):
            #print('ipaths: ',ipaths,'\tip: ',ip) # debug
            if len(p)-1>=network_depth and active_io_channels[io_channels[ipaths][ip]]==True:
                child=larpix.key.Key(io_group, io_channels[ipaths][ip], p[network_depth])
                parent=larpix.key.Key(io_group, io_channels[ipaths][ip], 0)
                #reverse_chain[child]=[]
                #current_depth=network_depth
                #while current_depth>=0:
                #    network_key=larpix.key.Key(io_group, io_channels[ipaths][ip], p[current_depth])
                #    reverse_chain[child].append(network_key)
                #    current_depth-=1
                if network_depth!=0:
                    parent=larpix.key.Key(io_group, io_channels[ipaths][ip], p[network_depth-1])
                child_chips.append( child )
                parent_chips.append( parent )
                chip_at_depth=True
        if chip_at_depth==False: break
#    print('REVERSE CHAIN: ',reverse_chain) # debug
    return child_chips, parent_chips#, reverse_chain

    
def check_networks(c, io, io_group, io_channels, tile_graphs, anode_paths):
    print('checking ',len(c.chips),' chips in network') # debug
    active_io_channels, valid = {}, {}
    for ioc in np.array(io_channels).flatten():
        active_io_channels[ioc]=True
        valid[ioc]=True

    # set ASIC clk_ctrl to 2.5 MHz from last chip in network back to root chip
    ds_network=downstream_network(c, anode_paths, io_group, io_channels)        
    reverse_traverse_larpix_transmit_clock(c, ds_network, 1)
    set_pacman_transmit_clock(io, io_channels, 20)

    network_depth=-1 # root chip at depth==0
    while any(active_io_channels.values()):
        network_depth+=1
        child_chips, parent_chips = chips_by_network_depth(network_depth, anode_paths, \
                                                           io_group, active_io_channels, \
                                                           io_channels)
        child_ioc=[child.io_channel for child in child_chips]
        for ioc in active_io_channels.keys():
            if ioc not in child_ioc: active_io_channels[ioc]=False
        if any(active_io_channels.values())==False: break

        # enforce configuration on all parent chips at child depth n
        if network_depth!=0:
            parent_registers=[]
            for parent in parent_chips:
                for i in range(c[parent].config.num_registers):
                    parent_registers.append( (parent, i) )
            ok, diff = c.enforce_registers(parent_registers, timeout=_timeout_, \
                                           connection_delay=_connection_delay_, \
                                           n=5, n_verify=5)
            for i in range(len(parent_chips)):
                tile=io_channel_to_tile(parent_chips[i].io_channel)
                if parent_chips[i] in diff.keys() and len(diff[parent_chips[i]])>0:
                    tile_graphs[tile].add_onesided_excluded_link( (parent_chips[i].chip_id, child_chips[i].chip_id) )
                    active_io_channels[parent_chips[i].io_channel]=False
                    valid[parent_chips[i].io_channel]=False
                    print('\t ==> IO CHANNEL INACTIVATED (from parent): ',parent_chips[i].io_channel) # DEBUG

        # enforce configuration on all chips at depth n
        child_registers=[]
        for child in child_chips:
            if active_io_channels[child.io_channel]==False: continue
            for i in range(c[child].config.num_registers):
                child_registers.append( (child, i) )
        ok, diff = c.enforce_registers(child_registers, timeout=_timeout_, \
                                       connection_delay=_connection_delay_, \
                                       n=5, n_verify=5)
        for i in range(len(child_chips)):
            tile=io_channel_to_tile(child_chips[i].io_channel)
            if child_chips[i] in diff.keys() and len(diff[child_chips[i]])>0:
                tile_graphs[tile].add_onesided_excluded_link( (parent_chips[i].chip_id, child_chips[i].chip_id) )
                active_io_channels[child_chips[i].io_channel]=False
                valid[child_chips[i].io_channel]=False
                print('\t ==> IO CHANNEL INACTIVATED (from child): ',child_chips[i].io_channel) # DEBUG
                c.remove_chip(child_chips[i])
            else: # if enforce is successful
                tile_graphs[tile].add_good_connection( (parent_chips[i].chip_id,
                                                      child_chips[i].chip_id) )

    return all(valid.values())


def write_networks(c, io, io_group, io_channels, tile_graphs, anode_paths):
    active_io_channels = {}
    for ioc in np.array(io_channels).flatten(): active_io_channels[ioc]=True
    
    network_depth=-1 # root chip at depth==0
    while any(active_io_channels.values()):
        network_depth+=1
        child_chips, parent_chips = chips_by_network_depth(network_depth, anode_paths, \
                                                           io_group, active_io_channels, \
                                                           io_channels)
        
        child_ioc=[child.io_channel for child in child_chips]
        for ioc in active_io_channels.keys():
            if ioc not in child_ioc: active_io_channels[ioc]=False
        if any(active_io_channels.values())==False: break
        
        ##### write larpix UART config @ 5 MHz #####
        if network_depth==0: setup_origin_chips(c, child_chips)
        else: setup_added_chips(c, tile_graphs, parent_chips, child_chips)

    return
            

def reset_larpix_transmit_clock_controller(c, io, io_group, io_channels, divisor):
    for i in range(2):
        io.reset_larpix(length=1024, io_group=_io_group_) # 100-microsecond hard reset
        time.sleep(0.2)
    set_pacman_transmit_clock(io, io_channels, divisor)
    c.chips.clear()
    

def main(verbose=_default_verbose, \
         **kwargs):
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True)
    
    power_on_reset(c, c.io)
    pacman_ioc = pacman_io_channels()
    set_pacman_transmit_clock(c.io, pacman_ioc, 10)

    ########## CONFIGURE HYDRA NETWORK ##########
    tile_graphs = setup_graphs_class()
#    log_reconcile = enable_logger(c, reconcile=True)
    start_setup=time.time()
    anode_paths, io_channels = [], []
    tile_root_chips={}
    for tile in range(len(pacman_ioc)):
        ioc_cid=zip(pacman_ioc[tile], _root_chip_ids_)
        root_chips, tile_io_channels = [], []
        ### !!!!! REPLACE WITH MULTIWRITE TO ALL ROOT CHIPS !!!!! ###
        for i in ioc_cid:
            chip_key=setup_root_chip(c, _io_group_, i[0], i[1]) # clk ctrl set to 1 (2.5 MHz)
            set_pacman_transmit_clock(c.io, [[chip_key.io_channel]] , 20)
            ok = reconcile_software_to_asic(c, chip_key, verbose)
            if ok:
                root_chips.append(chip_key.chip_id)
                tile_io_channels.append(chip_key.io_channel)
                if tile+1 not in tile_root_chips:
                    tile_root_chips[tile+1]=[]
                tile_root_chips[tile+1].append(chip_key.chip_id)
            if not ok: c.remove_chip(chip_key)
        io_channels.append(tile_io_channels)
    print(len(c.chips),' root chips configured')

    for tile in tile_root_chips.keys():
        existing_paths=[[chip] for chip in tile_root_chips[tile]]
        paths=tile_graphs[tile].get_path(existing_paths)
        anode_paths.append(paths)
    
    reset_larpix_transmit_clock_controller(c, c.io, _io_group_, pacman_ioc, 10)
    ok=False
    iteration_ctr=0
    while not ok:
        iteration_ctr+=1
        print('==========WRITE/CHECK NETWORK ITERATION: ',iteration_ctr,'\t ==========')
        write_networks(c, c.io, _io_group_, io_channels, tile_graphs, anode_paths)
        ok = check_networks(c, c.io, _io_group_, io_channels, tile_graphs, anode_paths)
        if not ok:
            reset_larpix_transmit_clock_controller(c, c.io, _io_group_, pacman_ioc, 10)
            anode_paths=[]
            for tile in tile_root_chips.keys():
                existing_paths=[[chip] for chip in tile_root_chips[tile]]
                paths=tile_graphs[tile].get_path(existing_paths)
                anode_paths.append(paths)
    
#    if verbose: print('{:.1f} seconds to setup networks \
#    chip and reconcile configuration'.format(time.time()-start_setup))
#    disable_logger(log_reconcile)
    print(len(c.chips),' chips in network')

    return
    time.sleep(5)

    ########## READBACK TEST ##########
#    start_readback=time.time()
#    log_readback = enable_logger(c, reconcile=False)
#    disable_logger(log_readback)
#    if verbose: print('{:.1f} seconds to readback {:.0f} \
#    times'.format(time.time()-start_readback, _iterations_))
        

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', default=_default_verbose, \
                        action='store_true', help='''Verbosity flag''')
    args = parser.parse_args()
    main(**vars(args))

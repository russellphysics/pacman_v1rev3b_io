import larpix
import larpix.io
import time
import argparse

_default_single_chip=False
_default_verbose=False

_io_group_=1
_iterations_=1e3
_root_chip_ids_=[11,41,71,101]
_timeout_=0.01
_connection_delay_=0.01

def power_vddd(io):
    io.set_reg(0x00024131, 40605, io_group=_io_group_)
    io.set_reg(0x00024133, 40605, io_group=_io_group_)
    io.set_reg(0x00024135, 40605, io_group=_io_group_)
    io.set_reg(0x00024137, 40605, io_group=_io_group_)
    io.set_reg(0x00024139, 40605, io_group=_io_group_)
    io.set_reg(0x0002413b, 40605, io_group=_io_group_)
    io.set_reg(0x0002413d, 40605, io_group=_io_group_)
    io.set_reg(0x0002413f, 40605, io_group=_io_group_)
    io.set_reg(0x101c, 4, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1000000001, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1000000011, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1000000111, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1000001111, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1000011111, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1000111111, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1001111111, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x10, 0b1011111111, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x2014, 0xffffffff, io_group=_io_group_)
    io.set_reg(0x18, 0xffffffff, io_group=_io_group_)

    
def power_vdda(io):
    io.set_reg(0x00024130, 46020, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x00024132, 46020, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x00024134, 46020, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x00024136, 46020, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x00024138, 46020, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x0002413a, 46020, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x0002413c, 46020, io_group=_io_group_); time.sleep(1)
    io.set_reg(0x0002413e, 46020, io_group=_io_group_); time.sleep(1)


# from reset_board_get_controller function in hydra_chain.py
def hard_reset_set_transmit_speed(io, io_channels): 
    io.reset_larpix(length=10240)
    for tile in range(len(io_channels)):
        for ioc in io_channels[tile]:
            io.set_uart_clock_ratio(ioc, 10, io_group=_io_group_)

            
def module3_power_on(io, io_channels):
    power_vddd(io)
    power_vdda(io)
    hard_reset_set_transmit_speed(io, io_channels)

    
def power_on_reset(c, io):
    io.set_reg(0x2014, 0xffffffff, io_group=_io_group_) # disable trigger forwarding
    io.set_reg(0x18, 0xffffffff, io_group=_io_group_) # enable pacman uart
    io.double_send_packets=False

    # power-on reset
    io.set_reg(0x14, 1, io_group=_io_group_) #enable global power
    io.reset_larpix(length=100000000,io_group=_io_group_) # 10-second hard reset
    start=time.time()
    vdda_reg=[0x00024130, 0x00024132, 0x00024134, 0x00024136, \
              0x00024138, 0x0002413a, 0x0002413c, 0x0002413e]
    vddd_reg=[0x00024131, 0x00024133, 0x00024135, 0x00024137, \
              0x00024139, 0x0002413b, 0x0002413d, 0x0002413f]
    vdda_dac=46020 #0
    for reg in vdda_reg: io.set_reg(reg, vdda_dac, io_group=_io_group_)
    vddd_dac=37105 # 40605
    for reg in vddd_reg: io.set_reg(reg, vddd_dac, io_group=_io_group_)
    enable_val=[0b1000000001, 0b1000000011, 0b1000000111, 0b1000001111,
                0b1000011111, 0b1000111111, 0b1001111111, 0b1011111111]
    for val in enable_val: io.set_reg(0x10, val, io_group=_io_group_); time.sleep(1) # enable tile power
    io.set_reg(0x101c, 4, io_group=_io_group_) # enable clock
    time.sleep(3)
    print('ready ',time.time()-start,' seconds since hard reset initiated')
    
    # double reset
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
    #c[chip_key].config.enable_mosi=[1]*4 # ***test***
    c.write_configuration(chip_key, 'enable_mosi')

    c[chip_key].config.enable_miso_upstream=[0]*4
    #c[chip_key].config.enable_miso_upstream=[1]*4 # ***test***
    c.write_configuration(chip_key,'enable_miso_upstream')
    c[chip_key].config.enable_miso_downstream=[1,0,0,0]
    #c[chip_key].config.enable_miso_downstream=[1]*4
    c.write_configuration(chip_key,'enable_miso_downstream')
    #c[chip_key].config.enable_miso_differential=[1]*4 # ***test***
    c[chip_key].config.enable_miso_differential=[1,0,0,0]
    c.write_configuration(chip_key,'enable_miso_differential')

    c[chip_key].config.clk_ctrl=1
#    c[chip_key].config.clk_ctrl=0 # ***test***
    c.write_configuration(chip_key, 'clk_ctrl')
        
    return chip_key


def reconcile_software_to_asic(c, chip_key):
    chip_key_registers=[(chip_key, i) \
                        for i in range(c[chip_key].config.num_registers)]
    ok, diff = c.enforce_registers(chip_key_registers, timeout=_timeout_,\
                                   connection_delay=_connection_delay_,\
                                   n=5, n_verify=5)
    if not ok: print(chip_key,' FAILED CONFIGURATION')
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


def single_chip_readback_test(c, chip_key):
    ctr=0
    while ctr<_iterations_:
        for i in range(65):
            if ctr==_iterations_: break
            ctr+=1
            c.multi_read_configuration( [(chip_key, i)], timeout=_timeout_,
                                        connection_delay=_connection_delay_)
            if ctr%100==0: print('iteration: ',ctr)

            
def multichip_readback_test(c):
    ctr=0
    while ctr<_iterations_:
        for i in range(65):
            if ctr==_iterations_: break
            ctr+=1
            chip_config_pairs=[]
            for chip_key in c.chips: chip_config_pairs.append( (chip_key, i) )
            c.multi_read_configuration( chip_config_pairs, timeout=_timeout_,
                                        connection_delay=_connection_delay_ )
            if ctr%100==0: print('iteration: ',ctr)
            

def pacman_io_channels():
    ctr=0; io_channels=[]; temp=[]
    for i in range(1,33,1):
        ctr+=1; temp.append(i)
        if ctr==4:
            io_channels.append(temp)
            temp=[]; ctr=0
    return io_channels


def set_transmit_clock(io, io_channels, divisor):
    for tile in range(len(io_channels)):
        for ioc in io_channels[tile]:
            io.set_uart_clock_ratio(ioc, divisor, io_group=_io_group_)

def main(single_chip=_default_single_chip, \
         verbose=_default_verbose, \
         **kwargs):
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True)
    io_channels=pacman_io_channels()
    
    power_on_reset(c, c.io)

    return ### TEST: REMOVE ME
    
    set_transmit_clock(c.io, io_channels, 10)

    #module3_power_on(c.io, io_channels) # ***test***
    
    ########## CONFIGURE HYDRA NETWORK ##########
    log_reconcile = enable_logger(c, reconcile=True)
    start_setup=time.time()
    if single_chip:
        chip_key=setup_root_chip(c, _io_group_, 5, 11)
        set_transmit_clock(c.io, [[chip_key.io_channel]] , 20)
        ok = reconcile_software_to_asic(c, chip_key)
    else:
        for tile in range(len(io_channels)):
            ioc_cid=zip(io_channels[tile], _root_chip_ids_)
            for i in ioc_cid:
                chip_key=setup_root_chip(c, _io_group_, i[0], i[1])
                set_transmit_clock(c.io, [[chip_key.io_channel]] , 20)
                ok = reconcile_software_to_asic(c, chip_key)
    
    if verbose: print('{:.1f} seconds to setup root \
    chip and reconcile configuration'.format(time.time()-start_setup))
    disable_logger(log_reconcile)
    print(len(c.chips),' chips in network')

    time.sleep(5)

    ########## READBACK TEST ##########
    start_readback=time.time()
    log_readback = enable_logger(c, reconcile=False)
    if single_chip: single_chip_readback_test(c, chip_key)
    else: multichip_readback_test(c); time.sleep(0.5)
    disable_logger(log_readback)
    if verbose: print('{:.1f} seconds to readback {:.0f} \
    times'.format(time.time()-start_readback, _iterations_))
        

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--single_chip', default=_default_single_chip, \
                        action='store_true', help='''Operate single chip''')
    parser.add_argument('--verbose', default=_default_verbose, \
                        action='store_true', help='''Verbosity flag''')
    args = parser.parse_args()
    main(**vars(args))

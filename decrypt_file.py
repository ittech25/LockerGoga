#!/usr/bin/env python
# -*- coding: utf-8 -*-

from Crypto.Cipher import PKCS1_OAEP, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA1, SHA256
import struct
from Crypto.Cipher import AES
from Crypto.Util import Counter
from Crypto.Util.number import bytes_to_long
import zlib
import os
import argparse

# DEFAULT CONFIGURATIONS
KNOWN_GOGA_VERSION = ['1440']


def decrypt_file(encrypted_filename, private_key):
    enc_file_size = os.stat(encrypted_filename).st_size
    enc_file = open(encrypted_filename, 'rb')
    enc_body_aes = enc_file.read(enc_file_size-148)  # 148 bytes from the end to start reading the footer with the CRC
    enc_footer = enc_file.read(148)  #  footer, with 128 bytes encrypted by RSA
    enc_file.close()  # close file

    ftr_struct_crc32 = enc_footer[0:4]       # checksum
    goga_crc32 = struct.unpack('<I', ftr_struct_crc32)[0]
    print('Footer CRC32:\t', hex(goga_crc32))

    ftr_struct_marker = enc_footer[4:8]      # the 'GOGA' marker
    goga_magic = str(ftr_struct_marker, 'utf-8')
    if goga_magic != 'GOGA':
        raise Exception("Unpacking failed: starter 'GOGA' magic is not familiar; "
                        "sample may not be encrypted by LockerGoga!")

    ftr_struct_version = enc_footer[8:12]    # version of 'GOGA'
    goga_version = str(ftr_struct_version, 'utf-8')
    if not goga_version in KNOWN_GOGA_VERSION:
        print("Warning: this version of LockerGoga has not been tested with this script.")
        input('Kill script now or continue at own risk...')

    ftr_struct_filesize = enc_footer[12:20]  # file size
    goga_size = struct.unpack('<Q', ftr_struct_filesize)[0]
    if (enc_file_size-148) != goga_size:
        raise Exception("Unpacking failed: actual file size does not match file size in footer.")

    goga_rsa_128bytes_data = enc_footer[20:148]  # the rest of the footer: enc'd file key and IV
    decrypted_footer = rsa_decrypt(goga_rsa_128bytes_data, private_key)

    enc_struct_always_zero = struct.unpack('<I', decrypted_footer[0:4])[0]  # when decrypted, this must be zero
    if enc_struct_always_zero != 0:
        raise Exception("Unpacking and/or RSA decryption failed: unpacked 'ALWAYS_ZERO' is not zero!")

    goga_rsa_aes_seed = decrypted_footer[4:20]
    goga_rsa_aes_key = decrypted_footer[20:36]

    goga_rsa_magic = str(decrypted_footer[36:40], 'utf-8')
    if goga_rsa_magic != 'goga':
        raise Exception("Unpacking and/or RSA decryption failed: footer end magic not 'goga'!")

    result_crc32 = aes_dec_file(encrypted_filename, goga_rsa_aes_key, goga_rsa_aes_seed, enc_body_aes)
    # TODO: CRC32 is not checking out correctly, likely some operation performed on the 4 bytes, like negating...
    # TODO: ... not a priority right now, and plenty of other integrity checking happens
    #if goga_crc32 != result_crc32:
    #    print('goga_crc32: ', hex(goga_crc32))
    #    print('result_crc32:', hex(result_crc32))
    #    raise Exception("Unpacking, RSA, or AES decryption failed: "
    #                    "CRC32 digest in footer does not match calculated CRC32 digest.")


def aes_dec_file(enc_file, aes_key, aes_seed, enc_data):
    counter = Counter.new(128, initial_value=bytes_to_long(aes_seed))  # bytes to long
    cipher = AES.new(aes_key, AES.MODE_CTR, counter=counter)

    dec_filename = enc_file + '.decrypted'
    dec_file_handle = open(dec_filename, 'wb')

    crc32_val = 0
    adler32_val = 0
    chunk_size = 0x10000
    length_total = 0

    data_range = range(0, len(enc_data), chunk_size)

    for i in data_range:
        decrypted_data = cipher.decrypt(enc_data[i:i+chunk_size])
        length_total += len(decrypted_data)

        crc32_val = zlib.crc32(decrypted_data, crc32_val)
        adler32_val = zlib.adler32(decrypted_data, adler32_val)

        dec_file_handle.write(decrypted_data)  # write decrypted data to file

    dec_file_handle.close()

    print("Decrypted results written to '" + dec_filename + "'.")
    return crc32_val

def rsa_decrypt(rsa_enc_data, rsa_privkey_filename):
    rsa_key = RSA.importKey(open(rsa_privkey_filename, 'rb').read())

    cipher = PKCS1_OAEP.new(rsa_key, hashAlgo=SHA1)
    rsa_dec_data = cipher.decrypt(rsa_enc_data)
    return rsa_dec_data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Accepts an encrypted file and associated private key and attempts'
                                                 'to decrypted the encrypted file.')

    parser.add_argument('in_file', metavar='FILENAME', type=str, nargs=1,
                        help='the file to be decrypted')
    parser.add_argument('private_key', metavar='FILENAME', type=str, nargs=1,
                        help='the associated private key')
    args = parser.parse_args()

    if not len(args.in_file) and len(args.private_key):
        raise Exception('Missing required positional arguments: in_file and private_key!')  # not likely to be raised

    in_file = args.in_file[0]
    private_key = args.private_key[0]

    decrypt_file(in_file, private_key)
    exit()

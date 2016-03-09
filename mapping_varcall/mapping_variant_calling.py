#!/usr/bin/env python
__author__ = 'thomasvangurp'
# Date created: 22/11/2014 (europe date)
# Function: Pipeline for mapping reads to reference
#Python version: 2.7.3
#External dependencies: samtools,pysam,methylation_calling.py
#Known bugs: None
#Modifications: None
import argparse
import subprocess
import tempfile
import os
import shutil
import sys
import pysam
from Bio import SeqIO


def getScriptPath():
    return os.path.dirname(__file__)

def parse_args():
    "Pass command line arguments"
    if not sys.argv[1:]:
        sys.argv.append('-h')
    parser = argparse.ArgumentParser(description='use bwameth for mapping reads')
    #input files
    parser.add_argument('-s','--sequences',
                        help='number of sequences to take for testing')
    parser.add_argument('--subsample_treshold',
                        help='Subsample treshold',default='100000')
    parser.add_argument('--tmpdir',
                        help='tmp directory',default="/tmp/")
    parser.add_argument('--input_dir',
                        help='optional: Choose input directory')
    parser.add_argument('--reads_R1',
                    help='Forward unmerged reads')
    parser.add_argument('--reads_R2',
                        help='Reverse unmerged reads')
    parser.add_argument('--merged',
                        help='merged watson and crick fastq')
    parser.add_argument('--reference',
                    help='reference clusters')
    parser.add_argument('--barcodes',
                    help='Barcodes used in output')
    parser.add_argument('--species',
                        help='Species: if selected only that species will be putin BAM RG header')
    parser.add_argument('-b','--bamout',
                        help='output for bam file with RGs')
    parser.add_argument('--threads',
                        help='Number of threads to used where multithreading is possible')
    parser.add_argument('--log',
                        help='log of output operation')
    parser.add_argument('--output_dir',
                        help='optional: Choose output directory')
    parser.add_argument('--watson_vcf',
                        help='watson vcf output')
    parser.add_argument('--crick_vcf',
                        help='crick vcf output')
    parser.add_argument('--snp_vcf',
                        help='vcf output snp')
    parser.add_argument('--methylation_vcf',
                        help='Methylation vcf output')
    parser.add_argument('--heatmap',
                        help='heatmap output methylation')
    args = parser.parse_args()
    if args.input_dir:
        args.reads_R1 = os.path.join(args.input_dir,'Unassembled.R1.watson_trimmed.fq.gz')
        args.reads_R2 = os.path.join(args.input_dir,'Unassembled.R2.crick_trimmed.fq.gz')
        args.merged = os.path.join(args.input_dir,'Assembled.trimmed.fq.gz')
        args.reference = os.path.join(args.input_dir,'cluster_consensus.renamed.fa')
    if args.output_dir:
        if not os.path.exists(args.output_dir):
            os.mkdir(args.output_dir)
        if not args.log:
            args.log = os.path.join(args.output_dir,'mapping_variantcalling.log')
        args.watson_vcf = os.path.join(args.output_dir,'watson.vcf')
        args.crick_vcf = os.path.join(args.output_dir,'crick.vcf')
        args.snp_vcf = os.path.join(args.output_dir,'snp.vcf')
        args.methylation_vcf = os.path.join(args.output_dir,'methylation.vcf')
        args.heatmap = os.path.join(args.output_dir,'heatmap.igv')
        #2 bed files should be made for subsequent analysis using Rnbeads or other software
        args.mastermeth = os.path.join(args.output_dir,'methylation.bed')
        args.mastersnp= os.path.join(args.output_dir,'snp.bed')
    return args

def run_subprocess(cmd,args,log_message):
    "Run subprocess under standardized settings"
    #force the cmds to be a string.
    if len(cmd) != 1:
        cmd = [" ".join(cmd)]
    with open(args.log,'a') as log:
        log.write("now starting:\t%s\n"%log_message)
        log.write('running:\t%s\n'%(' '.join(cmd)))
        log.flush()
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True,executable='/bin/bash')
        stdout, stderr = p.communicate()
        stdout = stdout.replace('\r','\n')
        stderr = stderr.replace('\r','\n')
        if stdout:
            log.write('stdout:\n%s\n'%stdout)
        if stderr:
            log.write('stderr:\n%s\n'%stderr)
        return_code = p.poll()
        if return_code:
            raise RuntimeError(stderr)
        log.write('finished:\t%s\n\n'%log_message)
    return 0

def make_header(in_files,args):
    """Make sam header given input file species and"""
    #parse input barcode file and make list of individuals

    in_files['header'] = 'location of header'
    return in_files

def run_bwameth(in_files,args):
    "run bwa_meth for mapping"

    in_files['bam_out'] = {}
    in_files['bam_out']['watson'] = os.path.join(args.output_dir,'watson.bam')
    in_files['bam_out']['crick'] = os.path.join(args.output_dir,'crick.bam')
    in_files['header'] = os.path.join(args.output_dir,'header.sam')
    #TEMP COMMANDS!
    # log = "get header"
    # cmd = ["samtools view -H %s > %s"%
    #        (('/Users/thomasvangurp/epiGBS/Baseclear/unfiltered_sequences/seqNNAtlE/Scabiosa/output_mapping/crick.bam'),
    #         (os.path.join(args.tmpdir,'header.sam')))]
    # run_subprocess(cmd,args,log)
    # return in_files
    #TEMP COMMANDS END!
    log = "index renamed reference using bwameth"
    ref = args.reference
    cmd = ['bwameth.py index %s'%ref]
    run_subprocess(cmd,args,log)

    log = "run bwameth for merged reads"
    if args.sequences:
        add = '|head -n %s'%(4*int(args.sequences))
    else:
        add = ''
    cmd = ['bwameth.py -t %s -p %s --reference %s <(gunzip -c %s %s) NA'%
           (args.threads,
            os.path.join(args.output_dir,'merged'),
            ref,
            args.merged,add
            )]
    run_subprocess(cmd,args,log)

    log = "run bwameth for non-merged reads"
    cmd = ['bwameth.py -t %s -p %s --reference %s <(gunzip -c %s %s) <(gunzip -c %s %s)'%
           (args.threads,
            os.path.join(args.output_dir,'pe'),
            ref,
            args.reads_R1,add,
            args.reads_R2,add
            )]
    run_subprocess(cmd,args,log)

    log = "get header"
    cmd = ["samtools view -H %s > %s"%
           ((os.path.join(args.output_dir,'pe.bam')),
            (os.path.join(args.output_dir,'header.sam')))]
    run_subprocess(cmd,args,log)


    log = "Append RG to header"
    in_files = addRG(in_files,args)

    log = "merge bam files"
    cmd = ["samtools merge -fc %s %s %s"%
           ((os.path.join(args.output_dir,'combined.bam')),
           "<(samtools reheader %s %s)"%(in_files['header'],os.path.join(args.output_dir,'merged.bam')),
           "<(samtools reheader %s %s)"%(in_files['header'],os.path.join(args.output_dir,'pe.bam')))]
    run_subprocess(cmd,args,log)





    log = "split in watson and crick bam file"
    cmd = ["samtools view -h %s |tee "%
           (os.path.join(args.output_dir,'combined.bam'))+
           ">( grep '^@\|ST:Z:Watson' | samtools view -Shb - > %s)"%
           (os.path.join(args.output_dir,'watson.bam'))+
           "| grep '^@\|ST:Z:Crick' | samtools view -Shb - > %s"%
           (os.path.join(args.output_dir,'crick.bam'))]

    run_subprocess(cmd,args,log)

    in_files['bam_out'] = {}
    in_files['bam_out']['watson'] = os.path.join(args.output_dir,'watson.bam')
    in_files['bam_out']['crick'] = os.path.join(args.output_dir,'crick.bam')


    log = "index watson bam file"
    cmd = ["samtools index %s"%in_files['bam_out']['watson']]
    run_subprocess(cmd,args,log)
    log = "index crick bam file"
    cmd = ["samtools index %s"%in_files['bam_out']['crick']]
    run_subprocess(cmd,args,log)
    return in_files


def addRG(in_files,args):
    "make header for output bamfile and split in watson and crick"
    #define readgroup header lines by combining the following
    species_name = ''
    """
    -
    read group
    ID*
    Unique read group identifier. The value of the ID field is used in the RG tags of alignment records.
    SM*
    Sample (use pool name where a pool is being sequenced)
    LB
    Library
    DS
    Description
    PU
    Platform unit (e.g. lane for Illumina or slide for SOLiD); should be a full, unambiguous identifier
    PI
    Predicted median insert size (maybe different from the actual median insert size)
    CN
    Name of sequencing center producing the read.
    DT
    Date the run was produced (ISO 8601 date or date/time).
    PL
    Platform/technology used to produce the read."""

    with open(args.barcodes,'r') as barcodes:
        sam_out= open(in_files['header'],'a')
        header = barcodes.readline().split('\t')
        for line in barcodes:
            RG = ['@RG']
            split_line = line.split('\t')
            if args.species:
                if split_line[(header.index('Species'))] != args.species:
                    continue
            fc = split_line[(header.index('Flowcell'))]
            lane = split_line[(header.index('Lane'))]
            sample = split_line[(header.index('Sample'))]
            RG.append('ID:%s_%s_%s'%(fc,lane,sample))
            RG.append('SM:%s'%(sample))
            RG.append('LB:%s_%s'%(fc,sample))
            RG.append('PL:ILLUMINA\n')
            sam_out.write('\t'.join(RG))
    sam_out.close()
    return in_files


def remove_PCR_duplicates(in_files,args):
    """Remove PCR duplicates and non-paired PE-reads per cluster"""
    for strand,bamfile in in_files['bam_out'].items():
        clusters = SeqIO.parse(open(args.reference),'fasta')
        handle = pysam.AlignmentFile(bamfile,'rb')
        dup_count = 0
        read_count = 0
        out_bam = tempfile.NamedTemporaryFile(suffix='uniq.bam',dir=args.output_dir,delete=False)
        out_handle = pysam.AlignmentFile(out_bam.name,'wb', template=handle)
        for cluster in clusters:
            reads = handle.fetch(cluster.id)
            if 'NNNNNNNN' in cluster._seq.upper():
                paired = True
            else:
                paired = False
            read_out = {}
            tags ={}
            for read in reads:
                tag = read.tags[-3][1]
                sample = read.tags[-1][1]
                AS = read.tags[1][1]
                #Get read ID and ID of potential pair
                if not read.is_proper_pair and paired:
                    continue
                read_id = '%s_%s'%(read.qname,read.is_read1)
                pair_id = '%s_%s'%(read.qname,read.is_read2)
                if sample not in tags:
                    tags[sample] = {}
                    read_out[sample] = {}
                if tag not in tags[sample]:
                    try:
                        #Store pair id for sample and locus specific tag
                        tags[sample][tag].append(pair_id)
                        read_out[sample][tag][AS] = read
                    except KeyError:
                        tags[sample][tag] = [pair_id]
                        read_out[sample][tag] = {AS:read}
                    #TODO: retain highest quality read instead of first read encountered
                    #TODO: get consensus of PCR duplicates?
                    # out_handle.write(read)
                    read_count += 1
                else:
                    if read_id in [read2_name for read2_name in tags[sample][tag]]:
                        #PE read with same name, write to output
                        out_handle.write(read)
                        read_count += 1
                    else:
                        dup_count += 1
        try:
            print '%s strand has %s reads %s duplicates which is %.1f%%'%(strand,
            read_count +dup_count,dup_count,(100*float(dup_count)/(read_count+dup_count)))
        except ZeroDivisionError:
            pass
        out_bam.flush()
        out_bam.close()
        old_bam = in_files['bam_out'][strand]
        log = "move old bam file %s to %s"%(old_bam,old_bam.replace('.bam','.old.bam'))
        cmd = ["mv %s %s"%(old_bam,old_bam.replace('.bam','.old.bam'))]
        run_subprocess(cmd,args,log)
        log = "move uniq bam file %s to %s"%(out_bam.name,old_bam)
        cmd = ["mv %s %s"%(out_bam.name,in_files['bam_out'][strand])]
        run_subprocess(cmd,args,log)
        log = "index bam file %s"%(old_bam)
        cmd = ["samtools index %s"%(in_files['bam_out'][strand])]
        run_subprocess(cmd,args,log)
    return in_files


def run_Freebayes(in_files,args):
    "run freebayes on watson and crick bam file with threadpool"
    in_files['variants'] = {}
    log = open(args.log,'a')
    for strand in ['watson','crick']:
        processes = set()
        max_processes = int(args.threads)
        outdir = tempfile.mkdtemp(prefix='vcf', dir=args.tmpdir)
        outlist = []
        in_files['variants'][strand] = outdir
        with open(in_files['header']) as header:
            for line in header:
                if line.startswith('@SQ'):
                    contig = line.split('\t')[1].split(':')[1]
                    length = line[:-1].split('\t')[2].split(':')[1]
                else:
                    continue
                #determine coverage on contig in bam file
                #set depth at 100.000.000
                bamfile = in_files['bam_out'][strand]
                cmd = ['samtools mpileup -d 10000000 %s -r %s:10-10'%(bamfile,contig)]
                if int(length) <500:
                    p = subprocess.Popen(cmd,stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE,shell=True,executable='/bin/bash')
                    stdout, stderr = p.communicate()
                    return_code = p.poll()
                    stderr = stderr.replace('\r','\n')
                    if return_code:
                        raise RuntimeError(stderr)
                    try:
                        out = stdout.split('\t')
                        depth = int(out[3])
                    except IndexError:
                        #no reads for this contig, skip
                        continue
                else:
                    # it does not make sense to calculate depth here!
                    depth = 0
                outlist.append('%s.vcf'%contig)
                #freebayes --bam  <(samtools view -hs 0.89552238806 /tmp/watson.bam 1|samtools view -Shb -)
                # --fasta-reference /Volumes/data/epiGBS/Baseclear/unfiltered_sequences/seqNNAtlE/Carrot/consensus.clustered.renamed.fa
                # -F 0 -E 1 -C 0 -G 0 --haplotype-length 1 -k -K -X -u -i -q 21 -w -a
                # --report-all-haplotype-alleles --report-monomorphic --report-genotype-likelihood-max
                cmd = """freebayes -f %s -F 0 -E 1 \
                -C 0 -G 0 --haplotype-length 1 \
                --report-all-haplotype-alleles --report-monomorphic\
                 --report-genotype-likelihood-max \
                --haplotype-length 1 -KkXuiwaq 21 """%\
                      (args.reference)
                if depth > int(args.subsample_treshold):
                    factor = int(args.subsample_treshold) / float(depth)
                    log = "Subsample bam file with high coverage"
                    bamfile = "--bam <(samtools view -hs %s %s %s|samtools view -Shb -)"%\
                              (factor,bamfile,contig)
                    cmd += " %s > %s"%\
                    (bamfile, os.path.join(outdir,'%s.vcf'%contig))
                # elif depth == 0:
                #     cmd += " --bam %s > %s"%\
                #     (bamfile, os.path.join(outdir,'%s.vcf'%contig))
                else:
                    cmd += " -r %s:0-%s --bam %s > %s"%\
                    (contig, int(length)-1,bamfile, os.path.join(outdir,'%s.vcf'%contig))
                log.write('starting freebayes on contig %s'%contig)
                log.flush()
                processes.add(subprocess.Popen(cmd,stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE,shell=True,executable='/bin/bash'))
                while len(processes) >= max_processes:
                    os.wait()
                    processes.difference_update([
                        p for p in processes if p.poll() is not None])
        #Make sure that all Freebayes processes are done before continuing to next st   ep.
        while len(processes):
            os.wait()
            processes.difference_update([
                        p for p in processes if p.poll() is not None])
        if strand == 'watson':
            target = args.watson_vcf
        else:
            target = args.crick_vcf
        print outdir,outlist[0],target
        shutil.move(os.path.join(outdir,outlist[0]),target)
        for vcf_file in outlist:
            file_in = os.path.join(outdir,vcf_file)
            cmd = ['cat %s |grep -v "^#" >> %s'%(file_in,target)]
            p = subprocess.Popen(cmd,stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,shell=True,executable='/bin/bash')
            stdout, stderr = p.communicate()
            return_code = p.poll()
            stdout = stdout.replace('\r','\n')
            stderr = stderr.replace('\r','\n')
            if return_code:
                raise RuntimeError(stderr)
        return in_files



def methylation_calling(in_files,args):
    "run methylation calling script."
    log = ["Run methylation calling script"]
    cmd = ["""
    python methylation_calling.py\
    -r      %(reference)s\
    -w      %(watson_vcf)s\
    -c      %(crick_vcf)s\
    -m      %(methylation_vcf)s\
    -s      %(snp_vcf)s\
    -heat   %(heatmap)s\
    -methylation_called %(mastermeth)s\
    -snp_called %(mastersnp)s"""%vars(args)]
    run_subprocess(cmd,args,log)
    return in_files

def main():
    "Main function loop"
    args = parse_args()
    test = 1
    if test:
        in_files = {}
        in_files['bam_out'] = {'watson':
       '/Users/thomasvangurp/epiGBS/Zwitserland/pilot_60/seq5U7ms_/Pru_vul/output_mapping/watson.bam',
       'crick':'/Users/thomasvangurp/epiGBS/Zwitserland/pilot_60/seq5U7ms_/Pru_vul/output_mapping/crick.bam'}
        remove_PCR_duplicates(in_files,args)
        in_files['header'] = '/Users/thomasvangurp/epiGBS/Zwitserland/pilot_60/seq5U7ms_/Pru_vul/output_mapping/header.sam'
        files = run_Freebayes(in_files,args)
        files = methylation_calling(files,args)
        sys.exit(0)
    #Make sure log is empty at start
    if os.path.isfile(args.log):
        os.remove(args.log)
    #Step 1: discover files in input #todo
    files = {}
    #Step 2: map reads using bwameth
    files = run_bwameth(files,args)
    #Step 3: join the non overlapping PE reads from watson and crick using usearch
    files = remove_PCR_duplicates(files,args)
    #Step 3a use seqtk to trim merged and joined reads from enzyme recognition site

    files = run_Freebayes(files,args)
    #Step 4: Dereplicate all watson and crick reads
    files = methylation_calling(files,args)
    print 'boe'
if __name__ == '__main__':
    main()

#!/usr/bin/env python
# __author__ = 'Bjorn Wouters'
# Date created: 16/09/2014 (europe date)
# Function: Base calling for methylated nucleotides and SNP's
#Python version: 2.7.3
#External modules: vcf, HTSeq
#Known bugs: None
#Modifications: None

import vcf
from vcf import utils
from itertools import izip
from Bio import SeqIO
import argparse
import re
import subprocess

# argparse used for commandline interpretation.
def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Process input files')
    parser.add_argument('-r', '--reference', type=str, nargs='?', default=None,
                        help='reference genome input.')
    parser.add_argument('-w', '--watson', type=str, nargs='?', default=None,
                        help='watson (top strand) .vcf file input.')
    parser.add_argument('-c', '--crick', type=str, nargs='?', default=None,
                        help='crick (bottom strand) .vcf file input.')
    parser.add_argument('-m', '--methylation_output', type=str, nargs='?', default=None,
                        help='Methylation vcf file output name')
    parser.add_argument('-s', '--SNP_output', type=str, nargs='?', default=None,
                        help='SNP vcf file output name')
    parser.add_argument('-heat', '--heatmap_output', type=str, nargs='?', default=None,
                        help='Heatmap igv file output name')
    parser.add_argument('-methylation_called', '-methylation_called', type=str, nargs='?', default=None,
                        help='Called sample information .txt file output name')
    parser.add_argument('-snp_called', '-snp_called', type=str, nargs='?', default=None,
                        help='Called sample information .txt file output name')
    parser.add_argument('-qual', '--min_quality', type=int, nargs='?', default=0,
                            help='Minimum Freebayes call quality before processing, default: 0')
    args = parser.parse_args()
    return args


def main():
    """Main function loop"""
    args = parse_args()
    files = parse_vcf(args)
    zip_tabix(args)

def filter_records(records):
    """filter variant calls on strand placement"""
    out_records = []
    for record in records:
        if not record.is_monomorphic:
            print 'Number of reference observations on the forward strand:\t%s'%record.INFO['SRF']
            print 'Number of reference observations on the reverse strand:\t%s'%record.INFO['SRR']
            print 'Strand balance probability for the reference allele:\t%s'%record.INFO['SRP']
            print 'Number of alternate observations on the forward strand:\t%s'%record.INFO['SAF']
            print 'Number of alternate observations on the reverse strand:\t%s'%record.INFO['SAR']
            print 'Strand balance probability for the alternate allele:\t%s'%record.INFO['SAP']

            print record

def parse_vcf(args):
    """
    Iterates through the given two vcf files. For each unique variant
    the scripts determines if it's a methylation or a SNP call or both.
    """
    methyl_called_file = open(args.methylation_called, 'w')
    snp_called_file = open(args.snp_called, 'w')
    watson_file = vcf.Reader(open(args.watson, 'r'))  # Watson input .vcf file
    crick_file = vcf.Reader(open(args.crick, 'r'))  # Crick input .vcf file
    reference_genome = SeqIO.to_dict(SeqIO.parse(args.reference, "fasta"))  # reference genome .fasta file
    methylation_file = vcf.Writer(open(args.methylation_output, 'w'),  # methylation output file
                                  watson_file, )
    snp_file = vcf.Writer(open(args.SNP_output, 'w'),  # snp output file
                          watson_file, )
    igv_file = open(args.heatmap_output, 'w')  # heatmap (igv) output file

    # Creates the header of the .igv file
    igv_file.write('#type=DNA_METHYLATION\n')
    samples = '\t'.join(watson_file.samples)
    igv_file.write('Chromosome\tStart\tEnd\tFeature\t' + samples + '\n')
    #Iterates through the watson file. If the variant is methylated (True); the script will write
    #the record in the methylation file. If the variant is not methylated (False); the script will write the
    #record in the snp file
    call_base = CallBase(watson_file, crick_file,
                         reference_genome, methylation_file,
                         snp_file, igv_file, methyl_called_file, snp_called_file)
    #use vcf.utils.walk_together
    combined_records = vcf.utils.walk_together(watson_file,crick_file)
    for records in combined_records:
        if None not in records:
            #both records need to be present and valid
            # qsum = sum(record.QUAL for record in records)
            # filter_records(records)
            call_base.watson_record,call_base.crick_record = records
            #Check for sum of quality of genotype alleles
            # if qsum < 30:
            #     if call_base.watson_record.REF in 'CG':
            #         #We should always check methylation variation, even if not variable!
            #         pass
            #     else:
            #         continue
            #Call methylation / SNPs: method of callbase class
            #TODO: check quality parameters elsewhere
            call_base.methylation_calling()
            quality_offset = args.min_quality
            min_alt_observations = 2
            # min_quality = call_base.set_offsets(quality_offset, min_alt_observations)
            call_base.write_records()

    # If there are no SNP's in the cluster/chromosome, the igv file needs to be written without a sliding window.
    if call_base.methylated_records:
        for sample in call_base.methylated_records:
            write_igv_file(call_base, sample)


def make_empty_sample(sample):
    """
    Returns an empty pyVCF sample for the given sample site.
    """
    return vcf.model._Call(sample.site,
                           sample.sample,
                           (None, None, None, None,
                            None, None, None))


def make_sample(sample, genotype):
    #TODO: CG context
    """
    Returns the current given sample with the corrected genotype.
    """
    return vcf.model._Call(sample.site,
                           sample.sample,
                           (genotype, sample.data.DP, sample.data.RO, sample.data.QR,
                            sample.data.AO, sample.data.QA, sample.data.GL))


def combine_record_samples(sample1, sample2):
    """
    Returns two sample records values together.
    """
    #TODO:implement merging function for SNP calling from watson/crick with methylation polymorphisms
    #TODO: Create records given that QR, QA, RO, AO are not available, only use AD and merge here. Check how AD records
    #TODO: are generated when multiple calls exist.
    if not sample1.called:
        depth = sample2.data.DP
        phred_quality_ref = sample2.data.QR
        phred_quality_alt = sample2.data.QA
        ref_observations = sample2.data.RO
        alt_observations = sample2.data.AO
    elif not sample2.called:
        depth = sample1.data.DP
        phred_quality_ref = sample1.data.QR
        phred_quality_alt = sample1.data.QA
        ref_observations = sample1.data.RO
        alt_observations = sample1.data.AO
    else:
        #Crude way of merging calldata from 2 records into new record..
        depth = sample1.data.DP + sample2.data.DP
        phred_quality_ref = sample1.data.QR + sample2.data.QR
        ref_observations = sample1.data.RO + sample2.data.RO
        try:
            if sample1.site.ALT.__len__() + sample2.site.ALT.__len__()<=2:
                phred_quality_alt = sample1.data.QA + sample2.data.QA
                alt_observations = sample1.data.AO + sample2.data.AO
            elif len(sample1.site.ALT) == 1 and len(sample2.site.ALT) > 1:
                try:
                    i = sample2.site.ALT.index(sample1.site.ALT[0])
                    alt_observations = sample1.data.AO + sample2.data.AO[i]
                    phred_quality_alt = sample1.data.QA + sample2.data.QA[i]
                except ValueError:
                    alt_observations = sample1.data.AO
                    phred_quality_alt = sample1.data.QA
            elif len(sample2.site.ALT) == 1 and len(sample1.site.ALT) > 1:
                try:
                    i = sample1.site.ALT.index(sample2.site.ALT[0])
                    alt_observations = sample2.data.AO + sample1.data.AO[i]
                    phred_quality_alt = sample2.data.QA + sample1.data.QA[i]
                except ValueError:
                    alt_observations = sample2.data.AO
                    phred_quality_alt = sample2.data.QA
            else:
                phred_quality_alt = []
                alt_observations = []
                for i,base in enumerate(sample1.site.ALT):

                    pq_alt = sample1.data.QA[i]
                    alt_obs = sample1.data.AO[i]
                    if base in sample2.site.ALT:
                        i2 = sample2.site.ALT.index(base)
                        pq_alt += sample2.data.QA[i2]
                        alt_obs += sample2.data.AO[i2]
                    phred_quality_alt.append(pq_alt)
                    alt_observations.append(alt_obs)

        except TypeError:
            return make_empty_sample(sample1)
    header = sample1.site.FORMAT
    header_list = header.split(':')
    call_data = vcf.model.make_calldata_tuple(header_list)
    values = [sample1.data[0], depth, ref_observations, phred_quality_ref,
                             alt_observations, phred_quality_alt, sample1.data.GL]
    if len(sample1.site.ALT) > len(sample2.site.ALT):
        model = vcf.model._Call(sample1.site,
                            sample1.sample,
                            call_data(*values))
    else:
        model = vcf.model._Call(sample2.site,
                            sample2.sample,
                            call_data(*values))
    return model


def write_igv_file(call_base, methyl_record):
    """
    Object function to write the record values to a heatmap (.igv file)
    """
    total_samples = 0
    processed_samples = {'CG': dict(), 'CHG': dict(), 'CHH': dict(), '.': dict()}
    methyl_pos = methyl_record.POS
    # If there are no SNP's at the given chromosome/cluster there is no dictionary key, so there are also no snp
    # positions in the chromosome/cluster
    if call_base.snp_record_dict.has_key(methyl_record.CHROM):
        snp_pos = set(pos.POS for pos in call_base.snp_record_dict[methyl_record.CHROM])
    else:
        snp_pos = set()

    def write_to_file(dataset, context):
        """
        Writes the given dataset to an .igv file with the right context.
        Dataset is a list with ratio's.
        """
        chr = methyl_record.CHROM
        # call_base.igv_file.write(str(chr) + '\t' + str(methyl_pos - 1) + '\t' + str(methyl_pos) + '\t' + context)
        out = '%s\t%s\t%s\t%s\t'%(chr,methyl_pos-1,methyl_pos,context)
        out += '\t'.join([str(v) for v in dataset]) + '\n'
        call_base.igv_file.write(out)
        # for value in dataset:
        #     if value == '.': # If there's no call, the value is set to '.'
        #         call_base.igv_file.write('\t.')
        #     else:
        #         call_base.igv_file.write('\t'+str(value))
        # call_base.igv_file.write('\n')

    def write_sample_data(sample_data, context, total_samples):
        """
        Writes a file with for each called sample the total calls and methylated calls.
        """
        chr = methyl_record.CHROM
        call_base.samples_called.write(str(chr) + '\t' + str(methyl_pos) + '\t' + context + '\t' + str(total_samples))
        for value in sample_data:
            if not isinstance(value, basestring):
                call_base.samples_called.write('\t'+'\t'.join(map(str, value)))
            else:
                call_base.samples_called.write(value)
        call_base.samples_called.write('\n')

    def calc_context(ref,pos):
        """
        If there are no SNP's neighbouring the methylation call, the context can be called
        by using the reference genome.
        """
        slice_start = max(pos-3,0) #negative positions excluded
        slice_end = pos+2
        reference_bases = call_base.reference_genome[methyl_record.CHROM].seq[slice_start:slice_end]
        if ref == 'G':
            ref_context = reference_bases[0:2][::-1]
            if re.match('C.', str(ref_context)):
                context = 'CG'
            elif re.match('[ATG]C', str(ref_context)):
                context = 'CHG'
            else:
                context = 'CHH'
        elif ref == 'C':
            ref_context = reference_bases[3:5]
            if re.match('G.', str(ref_context)):
                context = 'CG'
            elif re.match('[ATC]G', str(ref_context)):
                context = 'CHG'
            else:
                context = 'CHH'
        else:
            context = '.'
        return context

    def calc_methylated_observations(sample):
        if methyl_record.REF in 'CG':
            return sample.data.RO
        else:
            if sample.gt_bases[-1] in 'CG':
                if not isinstance(sample.data.AO, int):
                    float_index = int(sample.gt_alleles[1])-1
                    return sample.data.AO[float_index]
                else:
                    sample.data.AO
            else:
                return 0

    def calc_alt_observations(sample):
        try:
            if sample.site.REF == 'C':
                if 'T' in sample.site.ALT:
                    if not isinstance(sample.data.AO, int):
                        float_index = sample.site.ALT.index('T')
                        return sample.data.RO+sample.data.AO[float_index]
                    else:
                        return sample.data.RO+sample.data.AO
                else:
                    return sample.data.RO
            elif sample.site.REF == 'G':
                if 'A' in sample.site.ALT:
                    if not isinstance(sample.data.AO, int):
                        float_index = sample.site.ALT.index('A')
                        return sample.data.RO+sample.data.AO[float_index]
                    else:
                        return sample.data.RO+sample.data.AO
                else:
                    return sample.data.RO
            else:
                if sample.gt_bases[-1] == 'C':
                    if not isinstance(sample.data.AO, int):
                        C_index = sample.site.ALT.index('C')
                        T_index = sample.site.ALT.index('T')
                        return sample.data.AO[C_index]+sample.data.AO[T_index]
                    else:
                        return sample.data.AO
                elif sample.gt_bases[-1] == 'G':
                    if not isinstance(sample.data.AO, int):
                        G_index = sample.site.ALT.index('G')
                        A_index = sample.site.ALT.index('A')
                        return sample.data.AO[G_index]+sample.data.AO[A_index]
                    else:
                        return sample.data.AO
                else:
                    return 0
        except TypeError:
            return sample.data.RO

    def calc_ratio(sample):
        """
        Calculated the methylation ratio by dividing the methylated counts by total (methylated+unmethylated) counts.
        In case of a SNP the count of the alternate allele will not be taken into account for determining the ratio!
        """
        try:
            if methyl_record.REF == 'C':
                if sample.data.RO == 0:
                    return 0
                if 'T' in methyl_record.ALT:
                    if not isinstance(sample.data.AO, int):
                        float_index = methyl_record.ALT.index('T')
                        float_number = float(sample.data.RO) / float((sample.data.RO+sample.data.AO[float_index]))
                    else:
                        float_number = float(sample.data.RO) / float((sample.data.RO+sample.data.AO))
                else:
                    float_number = 1
            elif methyl_record.REF == 'G':
                if sample.data.RO == 0:
                    return 0
                if 'A' in methyl_record.ALT:
                    if not isinstance(sample.data.AO, int):
                        float_index = methyl_record.ALT.index('A')
                        float_number = float(sample.data.RO) / float((sample.data.RO+sample.data.AO[float_index]))
                    else:
                        float_number = float(sample.data.RO) / float((sample.data.RO+sample.data.AO))
                else:
                    float_number = 1
            else:
                if sample.gt_bases[-1] == 'C':
                    if not isinstance(sample.data.AO, int):
                        C_index = methyl_record.ALT.index('C')
                        T_index = methyl_record.ALT.index('T')
                        float_number = float(sample.data.AO[C_index]) / float((sample.data.AO[C_index]+sample.data.AO[T_index]))
                    else:
                        float_number = 1
                elif sample.gt_bases[-1] == 'G':
                    if not isinstance(sample.data.AO, int):
                        G_index = methyl_record.ALT.index('G')
                        A_index = methyl_record.ALT.index('A')
                        float_number = float(sample.data.AO[G_index]) / float((sample.data.AO[G_index]+sample.data.AO[A_index]))
                    else:
                        float_number = 1
                else:
                    float_number = 0
            ratio = "%.3f" % float_number
        except IndexError:
            ratio = "0.00"
        except TypeError:
            ratio = "0.00"
        return ratio

    def get_snp_sample_genotype(current_pos, sample_name):
        """
        Returns the sample of the SNP at the given position.
        """
        record = next((record for record in call_base.snp_record_dict[methyl_record.CHROM]
                       if record.POS == current_pos), None)
        sample = next((sample for sample in record.samples if sample.sample == sample_name), None)
        if not sample.called:
            return None
        try:
            return sample.gt_bases
        except IndexError:
            #TODO: break here and see what causes this!
            return None

    for sample in methyl_record.samples:
        sample_name = sample.sample
        if sample.called:
            total_samples += 1
            if methyl_record.REF in 'CG':
                ref = sample.site.REF
            else:
                ref = sample.gt_alleles[-1]

            if ref == 'C':
                p1 = 1
                p2 = 2
                alt_chk = 'G'
                ref_chk = 'A'
            elif ref == 'G':
                p1 = -1
                p2 = -2
                alt_chk = 'C'
                ref_chk = 'T'
            else:
                continue
            context = calc_context(ref,methyl_record.POS)
            if methyl_pos+p1 not in snp_pos and methyl_pos+p2 not in snp_pos:
                #No SNPs are found for this sample in 2 downstream adjacent positions
                context = calc_context(ref,methyl_record.POS)
                #TODO: define output for raw numbers instead of ratio!
                ratio = calc_ratio(sample)
                processed_samples[context].update({sample_name: ratio})
                continue
            if methyl_pos+p1 in snp_pos:
                gt = get_snp_sample_genotype(methyl_pos+p1, sample_name)
                if gt:
                    alt = gt[-1]
                    ref = gt[0]
                    if alt == alt_chk:
                        if ref == ref_chk:
                            context = '.'
                        else:
                            #Assume that SNP is CG as this is most common. TODO: determine if valid!
                            context = 'CG'
                    ratio = calc_ratio(sample)
                    processed_samples[context].update({sample_name: ratio})
                    continue
            if methyl_pos+p2 in snp_pos:
                gt = get_snp_sample_genotype(methyl_pos+p2, sample_name)
                if gt:
                    alt = gt[-1]
                    ref = gt[0]
                    if alt == alt_chk:
                        if ref == ref_chk:
                            context = '.'
                        else:
                            context = 'CHG'
                ratio = calc_ratio(sample)
                processed_samples[context].update({sample_name: ratio})

    for context in processed_samples:
        #Context can be CG,CHG,CHH or unknown:.
        if processed_samples[context]: #false if empty
            ratio_dataset = []
            sample_data = []
            for sample in methyl_record.samples:
                sample_name = sample.sample
                if sample_name in processed_samples[context]:
                    sample_ratio = processed_samples[context][sample_name]
                    ratio_dataset.append(sample_ratio)
                    sample_data.append([calc_methylated_observations(sample), calc_alt_observations(sample)])
                else:
                    ratio_dataset.append('.')
                    sample_data.append('\tNone\tNone')
            write_to_file(ratio_dataset, context)
            write_sample_data(sample_data, context, total_samples)


def write_snp_file(call_base, snp_record):
    snp_dict = {'A': dict(), 'T': dict(), 'G': dict(), 'C': dict()}

    total_samples = 0

    for sample in snp_record.samples:
        if sample.called:
            #new field is sample.AD sample.data.AO does no longer exist
            if isinstance(sample.data.AO,list):
                if sum(sample.data.AO) > 0:
                    total_samples += 1
                for i, alt_base in enumerate(sample.site.ALT):
                    snp_dict[str(alt_base)].update({sample.sample: sample.data.AO[i]})
            elif isinstance(sample.data.AO, int):
                if sample.data.AO > 0:
                    total_samples += 1
                    alt_base = str(sample.site.ALT[0])
                    snp_dict[alt_base].update({sample.sample: sample.data.AO})

    call_base.snp_output_file.write(str(snp_record.CHROM) + '\t' + str(snp_record.POS) +
                                    '\t' + str(total_samples))

    for sample in snp_record.samples:
        sample_name = sample.sample
        for base in snp_dict.keys():
            if sample_name in snp_dict[base]:
                call_base.snp_output_file.write('\t'+str(snp_dict[base][sample_name]))
            else:
                call_base.snp_output_file.write('\t'+str(0))
    call_base.snp_output_file.write('\n')

class CallBase(object):
    def __init__(self, watson_file, crick_file, reference_genome,
                 methylation_file, snp_file, igv_file, called_file, snp_output):
        self.watson_file = watson_file
        self.crick_file = crick_file
        self.samples_called = called_file
        self.snp_output_file = snp_output
        self.samples_called.write('chr\tpos\tcontext\tsamples_called')
        self.snp_output_file.write('chr\tpos\tsamples_called')
        for sample in watson_file.samples:
            self.samples_called.write('\t'+sample+'_methylated')
            self.samples_called.write('\t'+sample+'_total')
            self.snp_output_file.write('\t'+sample+'_A')
            self.snp_output_file.write('\t'+sample+'_T')
            self.snp_output_file.write('\t'+sample+'_G')
            self.snp_output_file.write('\t'+sample+'_C')
        self.samples_called.write('\n')
        self.snp_output_file.write('\n')
        self.watson_record = None
        self.crick_record = None
        self.reference_genome = reference_genome
        self.methylation_file = methylation_file
        self.snp_file = snp_file
        self.igv_file = igv_file
        self.methylation_calls = {'C': set(['T/C', 'C/C', 'T/T']),
                                  'G': set(['A/G', 'G/G', 'A/A'])}
        self.snp_record_dict = dict()
        self.methylated_records = list()

    def set_offsets(self, qual_offset, min_alt_observations):
        """
        Sets the offset parameters of the call_base object.
        """
        self.qual_offset = qual_offset
        self.min_alt_observations = min_alt_observations
        return self.qual_offset

    def check_change_samtools_call(self,sample):
        """Check variant calling in samtools provided sample"""
        empty_sample = make_empty_sample(sample)
        header = ['GT','DP','AO','RO']
        call_data = vcf.model.make_calldata_tuple(header)

        values = ['1/0',100,90,10]
        model = vcf.model._Call(sample.site,
                                    sample.sample,
                                    call_data(*values))
        return model


    def methylation_calling(self):
        """
        Main base calling algorithm. Determines methylation/SNP status for each sample having a watson and crick record.
        """

        # If the sample is methylated, the processed_samples will be filled under the methylated key, or when it's
        # a normal SNP, it will be filled under the snp key or when it's both, under both.

        self.processed_samples = {key: {'methylated': None, 'snp': None} for key in self.watson_file.samples}
        # Determine the reference base at the position of the VCF call.
        ref_base = self.watson_record.REF
        #loop watson and crick record for combined samples.
        for watson_sample, crick_sample in izip(self.watson_record, self.crick_record):
            # If there are is no call for both the watson and crick record sample, continue as we can not determine
            # whether polymorphism is a SNP/methylation polymorphism.
            if not watson_sample.called or not crick_sample.called:
                continue
            if 'AD' in watson_sample.data._fields:
                #create empty CallData object
                watson_sample = self.check_change_samtools_call(watson_sample)
                crick_sample = self.check_change_samtools_call(crick_sample)


            # Assigning the right alt base to the records.
            alt_watson = watson_sample.gt_bases.split('/')[1]
            alt_crick = crick_sample.gt_bases.split('/')[1]

            sample_name = watson_sample.sample
            if ref_base == 'C':
                if alt_crick == 'C' and alt_watson in 'CT':
                    #Methylation in watson C/T No polymorphism in Crick: methylation
                    self.processed_samples[sample_name]['methylated'] = watson_sample
                    try:
                        #'AC' is not present in homozygous situations.
                        if sum(crick_sample.site.INFO['AC']) > 0:
                            #The Alternate alleles need to be called in at least one sample to be valid!
                            self.processed_samples[sample_name]['snp'] = crick_sample
                    except KeyError:
                        pass
                elif alt_crick == 'A':
                    if alt_watson == 'A':
                        #Both watson and crick records should contain information on this alternate allele
                        #records are combined and written
                        combined_record = combine_record_samples(watson_sample, crick_sample)
                        self.processed_samples[sample_name]['snp'] = combined_record
                    else:
                        #alt_crick contains another base, this SNP is valid if present in watson.
                        if alt_watson in crick_sample.site.ALT:
                            #Both watson and crick contain the same alternate allele, the SNP is real?
                            alt_index = crick_sample.site.ALT.index(alt_watson)
                            try:
                                crick_alt_pct = crick_sample.data.AO[alt_index] / float(crick_sample.data.DP)
                            except TypeError:
                                crick_alt_pct = crick_sample.data.AO / float(crick_sample.data.DP)
                            alt_index = watson_sample.site.ALT.index(alt_watson)
                            try:
                                watson_alt_pct = watson_sample.data.AO[alt_index] / float(watson_sample.data.DP)
                            except TypeError:
                                watson_alt_pct = watson_sample.data.AO / float(watson_sample.data.DP)
                            if watson_alt_pct != 0.0 and crick_alt_pct != 0.0:
                                if max(crick_alt_pct,watson_alt_pct)/min(crick_alt_pct,watson_alt_pct)< 1.5:
                                    self.processed_samples[sample_name]['snp'] = crick_sample
                                    #TODO: merge alt counts for watson and crick here
                            elif crick_alt_pct == 0.0:
                                #REF:C watson C/T/A called as C/T crick C/A
                                #We can call both SNP and methylation. SNP from crick reliable
                                #Watson information on C/T ratio informative for methylation call
                                self.processed_samples[sample_name]['snp'] = crick_sample
                                self.processed_samples[sample_name]['methylated'] = watson_sample
                            else:
                                pass
                                #Can this occur? TODO: check if this can be true
                        else:
                            #alt_crick = 'A' ref == 'C' and alt_watson not seen in alt_watson.
                            #Likely a C/G SNP for which one or both alleles got converted watson C>T crick G>A
                            #TODO: make new C/G SNP record combining watson and crick variation.

                            pass
                elif alt_watson == 'G' and alt_crick in 'AG':
                    #C/G polymorphism in watson, C/G or C/A in Crick
                    #SNP information from watson, Methylation information from Crick
                     #TODO: After SNP, methylation > SNP
                    self.processed_samples[sample_name]['snp'] = watson_sample
                    self.processed_samples[sample_name]['methylated'] = crick_sample
                elif crick_sample.gt_bases == 'C/A' and watson_sample.gt_bases == 'G/T':
                    #Situation: C/G SNP, both alleles unmethylated.on watson C gets converted to T on watson G to A..
                    #TODO: create combined record for both Watson and crick replacing alt in watson A=> G
                    # and crick C=>T
                    pass
                elif alt_watson == 'T':
                    if alt_crick == 'T':
                    #C/T variant in both watson and crick: SNP ==> only information from crick is reliable
                        self.processed_samples[sample_name]['snp'] = crick_sample
                        if set(watson_sample.gt_bases.replace('/','')) == set(['T']):
                            self.processed_samples[sample_name]['methylated'] = watson_sample
                    if alt_crick != 'T' and alt_crick != 'C':
                    #Watson contains C/T methylation polymorphism and potentially other information
                    #Step 1: We can call Methylation polymorphism, crick is not C/T!
                        self.processed_samples[sample_name]['methylated'] = watson_sample
                        #Step 2. Is the SNP supported in watson strand?
                        #Can we call the SNP?
                        if alt_crick in watson_sample.site.ALT:
                            alt_index = watson_sample.site.ALT.index(alt_crick)
                            alt_count = watson_sample.data.AO[alt_index]
                            alt_qsum = watson_sample.data.QA[alt_index]
                            t_count = watson_sample.data.AO[watson_sample.site.ALT.index('T')]
                            if alt_count > t_count:
                                self.processed_samples[sample_name]['snp'] = crick_sample
                                #TODO: merge alt counts for watson and crick here
            elif ref_base == 'G':
                #Watson is homozygous reference (i.e. no SNP) and crick has Methylation variation
                if alt_watson == 'G' and alt_crick in 'GA':
                    self.processed_samples[sample_name]['methylated'] = crick_sample
                    try:
                        #If one or more sample has an alternate allele call it for this individual as well
                        if sum(watson_sample.site.INFO['AC']) > 0:
                             self.processed_samples[sample_name]['snp'] = watson_sample
                    except KeyError:
                        pass
                elif alt_crick == 'A' and alt_watson == 'A':
                    #The watson sample contains information on a SNP, G/A crick not reliable for SNP
                    self.processed_samples[sample_name]['snp'] = watson_sample
                    #The crick allele can only be queried for methylation variation if it is fully converted
                    #this means that no G can be in the Genotype.
                    if set(crick_sample.gt_bases.replace('/','')) == set(['A']):
                        self.processed_samples[sample_name]['methylated'] = crick_sample
                elif alt_crick == 'T' and alt_watson == 'T':
                    combined_record = combine_record_samples(watson_sample,crick_sample)
                    self.processed_samples[sample_name]['snp'] = combined_record
                    #TODO: After SNP, methylation > SNP
                elif alt_watson == 'C' and alt_crick in 'CT':
                    self.processed_samples[sample_name]['snp'] = crick_sample
                    self.processed_samples[sample_name]['methylated'] = watson_sample
            elif ref_base == 'T':
                if alt_watson == 'T' and alt_crick == 'T':
                    #both samples have the reference allele
                    #Determine the allele count for the Alternate allele for the site
                    #If sum of alternate allele count > 0 ?? add relevant Allele to SNP output
                    if 'AC' in watson_sample.site.INFO and 'AC' in crick_sample.site.INFO:
                        #Only Crick contains the SNP, TODO: check if valid!
                        if sum(crick_sample.site.INFO['AC']) == 0 and sum(watson_sample.site.INFO['AC']) > 0:
                            self.processed_samples[sample_name]['snp'] = watson_sample
                        #Only Watson contains the SNP, TODO: check if valid!
                        elif sum(crick_sample.site.INFO['AC']) > 0 and sum(watson_sample.site.INFO['AC']) == 0:
                            self.processed_samples[sample_name]['snp'] = crick_sample
                        #Both contain the SNP, combine records, TODO: check if combination is warranted!
                        #Both watson and crick should contain the same type of non reference allele
                        elif sum(watson_sample.site.INFO['AC']) > 0 and sum(crick_sample.site.INFO['AC']) > 0:
                            combined_record = combine_record_samples(watson_sample,crick_sample)
                            self.processed_samples[sample_name]['snp'] = combined_record
                    elif 'AC' in watson_sample.site.INFO:
                        #Only watson contains the SNP,
                        #TODO: assert if valid. Only true if SNP is T/C!
                        self.processed_samples[sample_name]['snp'] = watson_sample
                    elif 'AC' in crick_sample.site.INFO:
                        #Only watson contains the SNP,
                        #TODO: assert if valid. Only true if SNP is T/G!
                        self.processed_samples[sample_name]['snp'] = crick_sample
                elif alt_watson == 'A' and alt_crick == 'A':
                    #TODO: check what is causing the error in combined_record it's not writing now.
                    combined_record = combine_record_samples(watson_sample,crick_sample)
                    # self.processed_samples[sample_name]['snp'] = combined_record
                    self.processed_samples[sample_name]['snp'] = watson_sample
                elif alt_watson == 'G' and alt_crick in 'GA':
                    self.processed_samples[sample_name]['snp'] = watson_sample
                    self.processed_samples[sample_name]['methylated'] = crick_sample
                elif alt_watson == 'C' and alt_crick in 'CT':
                    self.processed_samples[sample_name]['snp'] = crick_sample
            elif ref_base == 'A':
                if alt_watson == 'A' and alt_crick == 'A':
                    #both samples have the reference allele
                    #Determine the allele count for the Alternate allele for the site
                    #If sum of alternate allele count > 0 ?? add relevant Allele to SNP output
                    if 'AC' in watson_sample.site.INFO and 'AC' in crick_sample.site.INFO:
                        #Only Crick contains the SNP, TODO: check if valid!
                        if sum(crick_sample.site.INFO['AC']) == 0 and sum(watson_sample.site.INFO['AC']) > 0:
                            self.processed_samples[sample_name]['snp'] = watson_sample
                        #Only Watson contains the SNP, TODO: check if valid!
                        elif sum(crick_sample.site.INFO['AC']) > 0 and sum(watson_sample.site.INFO['AC']) == 0:
                            self.processed_samples[sample_name]['snp'] = crick_sample
                        #Both contain the SNP, combine records, TODO: check if combination is warranted!
                        #Both watson and crick should contain the same type of non reference allele
                        elif sum(watson_sample.site.INFO['AC']) > 0 and sum(crick_sample.site.INFO['AC']) > 0:
                            combined_record = combine_record_samples(watson_sample, crick_sample)
                            self.processed_samples[sample_name]['snp'] = combined_record
                    elif 'AC' in watson_sample.site.INFO:
                        #Only watson contains the SNP,
                        #TODO: assert if valid. Only true if SNP is A/G!
                        self.processed_samples[sample_name]['snp'] = watson_sample
                    elif 'AC' in crick_sample.site.INFO:
                        #Only watson contains the SNP,
                        #TODO: assert if valid. Only true if SNP is A/C!
                        self.processed_samples[sample_name]['snp'] = crick_sample
                elif alt_watson == 'T' and alt_crick == 'T':
                    combined_record = combine_record_samples(watson_sample,crick_sample)
                    self.processed_samples[sample_name]['snp'] = combined_record
                elif alt_crick == 'C' and alt_watson in 'CT':
                    self.processed_samples[sample_name]['snp'] = crick_sample
                    #self.processed_samples[sample_name]['methylated'] = watson_sample
                elif alt_watson == 'G' and alt_crick in 'GA':
                    self.processed_samples[sample_name]['snp'] = watson_sample
                    #self.processed_samples[sample_name]['methylated'] = crick_sample

    def write_records(self):
        """
        Writes the samples that are saved in the self.processed_samples variable.
        """
        # If the methylation or the snp variable in the unique sample is None, the None will
        # be replaced with an empty sample made by the function: make_empty_sample.
        for sample in self.watson_file.samples:
            index = self.crick_file.samples.index(sample)
            if self.processed_samples[sample]['methylated'] == None:
                record_sample = self.watson_record.samples[index]
                empty_sample = make_empty_sample(record_sample)
                self.processed_samples[sample]['methylated'] = empty_sample
            if self.processed_samples[sample]['snp'] == None:
                record_sample = self.watson_record.samples[index]
                empty_sample = make_empty_sample(record_sample)
                self.processed_samples[sample]['snp'] = empty_sample

        # Converts the dictionary to two separate lists with all the methylation and snp samples in it.
        methylated_samples = []
        snp_samples = []
        for sample in self.watson_file.samples:
            methylated_samples.append(self.processed_samples[sample]['methylated'])
            snp_samples.append(self.processed_samples[sample]['snp'])

        def define_record(self, samples):
            """
            Returns a pyVCF parsable record if a list of samples is given.
            """
            # Sets the record as a parent record depending on reference base.
            if self.watson_record and self.crick_record:

                if self.watson_record.REF == 'C':
                    vcf_file = self.watson_record
                elif self.watson_record.REF == 'G':
                    vcf_file = self.crick_record
                else:
                    vcf_file = self.watson_record
            else:
                vcf_file = self.watson_record

            chr = vcf_file.CHROM
            pos = vcf_file.POS
            id = vcf_file.ID
            ref = vcf_file.REF
            alt = vcf_file.ALT
            qual = vcf_file.QUAL
            filter = vcf_file.FILTER
            format = vcf_file.FORMAT
            sample_indexes = vcf_file._sample_indexes

            processed_record = vcf.model._Record(
                chr, pos, id, ref,
                alt, qual,
                filter, 0, format,
                sample_indexes, samples
            )

            return processed_record

        def define_record_snp(samples):
            """
            Returns a pyVCF parsable record if a list of samples is given.
            """
            # Sets the record as a parent record depending on reference base.
            vcf_file = samples[0].site

            chr = vcf_file.CHROM
            pos = vcf_file.POS
            id = vcf_file.ID
            ref = vcf_file.REF
            alt = vcf_file.ALT
            qual = vcf_file.QUAL
            filter = vcf_file.FILTER
            format = vcf_file.FORMAT
            sample_indexes = vcf_file._sample_indexes

            processed_record = vcf.model._Record(
                chr, pos, id, ref,
                alt, qual,
                filter, 0, format,
                sample_indexes, samples
            )

            return processed_record
        #TODO: check SNP calling here
        # if any(sample.called for sample in snp_samples):
        #     #Use different method here to make sure the number of ALT alleles matches if crick
        #     #and watson are different. #TODO: determine if this method can not be used always.
        #     snp_record = define_record_snp(snp_samples)
        #     write_snp_file(self, snp_record)
        #     self.snp_file.write_record(snp_record)
        #     #snp_record_dict is purely used to determine context for CG,CHG and CHH methylation.
        #     #It does not contain any useful information pertaining to SNPs
        #     if self.snp_record_dict.has_key(snp_record.CHROM) == True:
        #         self.snp_record_dict[snp_record.CHROM].append(snp_record)
        #     else:
        #         # self.snp_record_dict.clear()
        #         self.snp_record_dict[snp_record.CHROM] = [snp_record]
        if any(sample.called for sample in methylated_samples):
            methylation_record = define_record(self, methylated_samples)
            self.methylation_file.write_record(methylation_record)
            self.methylated_records.append(methylation_record)

        if self.snp_record_dict.has_key(self.watson_record.CHROM):
            if len(self.snp_record_dict[self.watson_record.CHROM]) >= 5:
                for record in self.methylated_records[:-2]:
                    write_igv_file(self, record)
                del self.methylated_records[:-2]
                del self.snp_record_dict[self.watson_record.CHROM][0]

def zip_tabix(args):
    """Zip and tabix index the output files"""
    cmds = ['bgzip -f %s'% args.methylation_output,
            'tabix -p vcf %s.gz'% args.methylation_output,
            'bgzip -f %s'% args.SNP_output,
            'tabix -p vcf %s.gz'% args.SNP_output
            ]
    for cmd in cmds:
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True,executable='/bin/bash')
        p.wait()

# If script is called; calls for the main
if __name__ == '__main__':
    main()